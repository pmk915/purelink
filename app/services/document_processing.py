from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import zlib
import zipfile
from xml.etree import ElementTree

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentProcessingStatus
from app.services.asr_provider import (
    ASRProviderError,
    DEFAULT_ASR_SAMPLE_RATE,
    resolve_asr_provider,
)
from app.services.chunk_metadata import (
    build_chunk_metadata_payload,
    build_source_locator,
    normalize_source_type,
)
from app.services.document import update_document_processing_status
from app.services.document_parsing import get_parser
from app.services.document_parsing.block_persistence import replace_document_blocks
from app.services.document_parsing.types import ParsedDocument
from app.services.ocr_provider import OCRProviderError, OCRRegion, resolve_ocr_provider
from app.services.text_quality import (
    TextQualityStatus,
    detect_text_quality,
    sanitize_text,
)


SUPPORTED_STANDARD_PROCESS_SUFFIXES = {
    ".txt": "text",
    ".md": "markdown",
    ".docx": "docx",
    ".pdf": "pdf",
}
OCR_PROCESS_SUFFIXES = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}
MEDIA_PROCESS_SUFFIXES = {
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".m4v": "video",
}
TIMED_TRANSCRIPT_SOURCE_TYPES = {"audio", "video"}
TEXT_ENCODING_CANDIDATES = ("utf-8", "utf-8-sig", "gb18030")
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 120
DIRECT_CHUNK_THRESHOLD = 1200
PDF_OCR_FALLBACK_MIN_CHARS = 16
PDF_OCR_RENDER_SCALE = 2.0
INLINE_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
MARKDOWN_LIST_MARKER_PATTERN = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[([^\]]*)\]\([^)]+\)")
MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(\*\*|__|\*|_|~~)")
SENTENCE_ENDING_CHARACTERS = {"。", "！", "？", "；", ".", "!", "?", ";"}
CLAUSE_ENDING_CHARACTERS = {"，", ",", "、", "：", ":"}
LOW_VALUE_CITATION_TEXTS = {
    "如下：",
    "因此。",
    "综上。",
    "该方法。",
}
PDF_OBJECT_PATTERN = re.compile(rb"(?ms)(\d+)\s+\d+\s+obj(.*?)endobj")
PDF_PAGE_TYPE_PATTERN = re.compile(rb"/Type\s*/Page\b")
PDF_PAGES_TYPE_PATTERN = re.compile(rb"/Type\s*/Pages\b")
PDF_CONTENTS_ARRAY_PATTERN = re.compile(rb"/Contents\s*\[(.*?)\]", re.S)
PDF_CONTENTS_SINGLE_PATTERN = re.compile(rb"/Contents\s+(\d+)\s+\d+\s+R")
PDF_CONTENT_REF_PATTERN = re.compile(rb"(\d+)\s+\d+\s+R")
PDF_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
PDF_BT_ET_PATTERN = re.compile(rb"BT(.*?)ET", re.S)
PDF_LITERAL_STRING_PATTERN = re.compile(rb"\((?:\\.|[^\\()])*\)")
PDF_HEX_STRING_PATTERN = re.compile(rb"<([0-9A-Fa-f\s]+)>")
WORDPROCESSINGML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}

logger = logging.getLogger("purelink.documents")
SUPPORTED_STANDARD_PROCESS_HINT = ".txt, .md, .docx, and .pdf"
ERROR_PDF_TEXT_GARBLED = "PDF_TEXT_GARBLED"
ERROR_PDF_TEXT_EXTRACTION_FAILED = "PDF_TEXT_EXTRACTION_FAILED"
ERROR_OCR_PROVIDER_UNAVAILABLE = "OCR_PROVIDER_UNAVAILABLE"
ERROR_OCR_NO_TEXT_FOUND = "OCR_NO_TEXT_FOUND"
ERROR_TEXT_QUALITY_TOO_LOW = "TEXT_QUALITY_TOO_LOW"
ERROR_CHUNK_PERSIST_FAILED = "CHUNK_PERSIST_FAILED"
ERROR_UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
ERROR_FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"


class DocumentProcessingError(ValueError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class ExtractedTextSegment:
    text: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class ExtractedTextResult:
    text: str
    source_type: str
    extractor: str
    extracted_char_count: int
    segments: tuple[ExtractedTextSegment, ...]
    encoding: str | None = None
    page_count: int | None = None


@dataclass(frozen=True, slots=True)
class GeneratedChunkPayload:
    chunk_key: str
    chunk_index: int
    chunk_text: str
    metadata_json: str | None


@dataclass(frozen=True, slots=True)
class GeneratedCitationUnitPayload:
    chunk_key: str
    unit_index: int
    unit_text: str
    start_char: int | None
    end_char: int | None
    metadata_json: str | None


@dataclass(frozen=True, slots=True)
class ProcessedDocumentResult:
    chunk_count: int
    citation_unit_count: int
    extracted_char_count: int
    extractor: str
    source_type: str
    encoding: str | None = None
    page_count: int | None = None


@dataclass(frozen=True, slots=True)
class PreparedTextSegment:
    text: str
    metadata: dict[str, object]
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True, slots=True)
class RenderedPDFPage:
    page_number: int
    image_path: Path


TextExtractor = Callable[..., ExtractedTextResult]
ProgressCallback = Callable[[str], None]


def _report_progress(
    progress_callback: ProgressCallback | None,
    step_name: str,
) -> None:
    if progress_callback is None:
        return
    progress_callback(step_name)


def process_document(
    db: Session,
    *,
    document: Document,
    upload_root: Path,
    progress_callback: ProgressCallback | None = None,
) -> ProcessedDocumentResult:
    source_path = upload_root / document.storage_path
    suffix = Path(document.original_filename).suffix.lower()
    source_type = resolve_source_type(suffix)
    if source_type is None:
        raise DocumentProcessingError(
            f"Only {SUPPORTED_STANDARD_PROCESS_HINT} documents are supported by this processing flow.",
            error_code=ERROR_UNSUPPORTED_FILE_TYPE,
        )

    update_document_processing_status(
        db,
        document=document,
        processing_status=DocumentProcessingStatus.PROCESSING,
        error_message=None,
        processed_at=None,
    )

    logger.info(
        "document process start document_id=%s knowledge_base_id=%s source_type=%s source_path=%s",
        document.id,
        document.knowledge_base_id,
        source_type,
        source_path,
    )

    current_step = "resolve_source"

    def report(step_name: str) -> None:
        nonlocal current_step
        current_step = step_name
        _report_progress(progress_callback, step_name)

    try:
        report("resolve_source")
        report("extract_text")
        parser = get_parser(filename=document.original_filename, mime_type=document.file_type)
        parsed_document = parser.parse(
            source_path,
            filename=document.original_filename,
            mime_type=document.file_type,
        )
        extracted = build_extracted_text_result_from_parsed_document(parsed_document)
        logger.info(
            "document text extracted document_id=%s knowledge_base_id=%s source_type=%s extractor=%s current_step=%s page_count=%s extracted_char_count=%s",
            document.id,
            document.knowledge_base_id,
            extracted.source_type,
            extracted.extractor,
            current_step,
            extracted.page_count,
            extracted.extracted_char_count,
        )
        report("persist_blocks")
        replace_document_blocks(
            db,
            document_id=document.id,
            blocks=parsed_document.blocks,
        )
        report("chunk_content")
        generated_chunks = chunk_extracted_text_result(
            extracted=extracted,
            document_id=document.id,
        )
        generated_citation_units = build_citation_unit_payloads(
            chunks=generated_chunks,
            document=document,
        )
        generated_citation_units = filter_generated_citation_units(
            citation_units=generated_citation_units,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
        )
        report("persist_chunks")
        replace_document_chunks(
            db,
            document=document,
            chunks=generated_chunks,
            citation_units=generated_citation_units,
        )
        report("finalize_document")
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.READY,
            error_message=None,
            processed_at=datetime.now(UTC),
        )
    except DocumentProcessingError as exc:
        db.rollback()
        logger.warning(
            "document process failed document_id=%s knowledge_base_id=%s source_type=%s current_step=%s error_code=%s error_type=%s reason=%s",
            document.id,
            document.knowledge_base_id,
            source_type,
            current_step,
            exc.error_code,
            type(exc).__name__,
            str(exc),
        )
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message=str(exc),
            processed_at=None,
        )
        raise
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected runtime failures
        db.rollback()
        logger.exception(
            "document process unexpected failure document_id=%s knowledge_base_id=%s source_type=%s current_step=%s error_type=%s",
            document.id,
            document.knowledge_base_id,
            source_type,
            current_step,
            type(exc).__name__,
        )
        error_code = (
            ERROR_CHUNK_PERSIST_FAILED
            if current_step == "persist_chunks"
            else ERROR_PDF_TEXT_EXTRACTION_FAILED
            if source_type == "pdf"
            else ERROR_TEXT_QUALITY_TOO_LOW
        )
        error_message = "Document processing failed unexpectedly."
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message=error_message,
            processed_at=None,
        )
        raise DocumentProcessingError(error_message, error_code=error_code) from exc

    logger.info(
        "document process completed document_id=%s knowledge_base_id=%s source_type=%s extractor=%s current_step=%s page_count=%s chunk_count=%s extracted_char_count=%s",
        document.id,
        document.knowledge_base_id,
        extracted.source_type,
        extracted.extractor,
        current_step,
        extracted.page_count,
        len(generated_chunks),
        extracted.extracted_char_count,
    )
    return ProcessedDocumentResult(
        chunk_count=len(generated_chunks),
        citation_unit_count=len(generated_citation_units),
        extracted_char_count=extracted.extracted_char_count,
        extractor=extracted.extractor,
        source_type=extracted.source_type,
        encoding=extracted.encoding,
        page_count=extracted.page_count,
    )


def process_txt_document(
    db: Session,
    *,
    document: Document,
    upload_root: Path,
    progress_callback: ProgressCallback | None = None,
) -> ProcessedDocumentResult:
    suffix = Path(document.original_filename).suffix.lower()
    if suffix != ".txt":
        raise DocumentProcessingError("Only .txt documents are supported by this processing flow.")
    return process_document(
        db,
        document=document,
        upload_root=upload_root,
        progress_callback=progress_callback,
    )


def resolve_source_type(suffix: str) -> str | None:
    if suffix in SUPPORTED_STANDARD_PROCESS_SUFFIXES:
        return SUPPORTED_STANDARD_PROCESS_SUFFIXES[suffix]
    settings = get_settings()
    if settings.enable_ocr and suffix in OCR_PROCESS_SUFFIXES:
        return OCR_PROCESS_SUFFIXES[suffix]
    if settings.enable_media and suffix in MEDIA_PROCESS_SUFFIXES:
        return MEDIA_PROCESS_SUFFIXES[suffix]
    return None


def resolve_text_extractor(suffix: str) -> TextExtractor:
    settings = get_settings()
    if suffix == ".txt":
        return extract_text_from_txt
    if suffix == ".md":
        return extract_text_from_md
    if suffix == ".docx":
        return extract_text_from_docx
    if suffix == ".pdf":
        return extract_text_from_pdf
    if suffix in OCR_PROCESS_SUFFIXES:
        if not settings.enable_ocr:
            raise DocumentProcessingError(
                "This PureLink Core deployment does not enable OCR processing.",
                error_code=ERROR_FEATURE_NOT_ENABLED,
            )
        return extract_text_from_image
    if suffix in MEDIA_PROCESS_SUFFIXES:
        if not settings.enable_media:
            raise DocumentProcessingError(
                "This PureLink Core deployment does not enable audio or video processing.",
                error_code=ERROR_FEATURE_NOT_ENABLED,
            )
    if suffix in {".mp3", ".wav", ".m4a"}:
        return extract_text_from_audio
    if suffix in {".mp4", ".mov", ".m4v"}:
        return extract_text_from_video
    raise DocumentProcessingError(
        f"Only {SUPPORTED_STANDARD_PROCESS_HINT} documents are supported by this processing flow.",
        error_code=ERROR_UNSUPPORTED_FILE_TYPE,
    )


def build_extracted_text_result_from_parsed_document(
    parsed_document: ParsedDocument,
) -> ExtractedTextResult:
    source_type = str(parsed_document.metadata.get("source_type") or "text")
    extractor = str(parsed_document.metadata.get("extractor") or parsed_document.metadata.get("parser") or "unknown")
    raw_segments = [
        ExtractedTextSegment(
            text=block.text,
            metadata={
                "source_type": source_type,
                **block.metadata,
                **({"source_locator": block.source_locator} if block.source_locator else {}),
                **({"heading_level": block.heading_level} if block.heading_level is not None else {}),
                "block_type": block.block_type.value,
            },
        )
        for block in parsed_document.blocks
        if block.text.strip()
    ]
    if not raw_segments and parsed_document.text.strip():
        raw_segments = [
            ExtractedTextSegment(
                text=parsed_document.text,
                metadata={"source_type": source_type},
            )
        ]
    return build_extracted_text_result(
        source_type=source_type,
        extractor=extractor,
        raw_segments=raw_segments,
        encoding=_coerce_optional_str(parsed_document.metadata.get("encoding")),
        page_count=_coerce_optional_int(parsed_document.metadata.get("page_count")),
    )


def _coerce_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _coerce_optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def extract_text_from_txt(*, source_path: Path) -> ExtractedTextResult:
    decoded_text, detected_encoding = read_text_file_with_fallback(source_path)
    return build_extracted_text_result(
        source_type="text",
        extractor="text",
        raw_segments=[
            ExtractedTextSegment(
                text=decoded_text,
                metadata={"source_type": "text"},
            )
        ],
        encoding=detected_encoding,
    )


def extract_text_from_md(*, source_path: Path) -> ExtractedTextResult:
    decoded_text, detected_encoding = read_text_file_with_fallback(source_path)
    current_heading: str | None = None
    paragraph_lines: list[str] = []
    raw_segments: list[ExtractedTextSegment] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph_text = " ".join(paragraph_lines).strip()
        if paragraph_text:
            metadata: dict[str, object] = {"source_type": "markdown"}
            if current_heading:
                metadata["section_title"] = current_heading
            raw_segments.append(
                ExtractedTextSegment(
                    text=paragraph_text,
                    metadata=metadata,
                )
            )
        paragraph_lines = []

    for raw_line in decoded_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue

        heading_match = MARKDOWN_HEADING_PATTERN.match(line)
        if heading_match is not None:
            flush_paragraph()
            current_heading = normalize_markdown_inline_text(heading_match.group(2))
            if current_heading:
                raw_segments.append(
                    ExtractedTextSegment(
                    text=current_heading,
                    metadata={
                        "source_type": "markdown",
                        "section_title": current_heading,
                    },
                )
                )
            continue

        paragraph_lines.append(normalize_markdown_inline_text(line))

    flush_paragraph()

    return build_extracted_text_result(
        source_type="markdown",
        extractor="markdown",
        raw_segments=raw_segments,
        encoding=detected_encoding,
    )


def extract_text_from_pdf(*, source_path: Path) -> ExtractedTextResult:
    raw_content = read_binary_file(source_path)
    if not raw_content.startswith(b"%PDF"):
        raise DocumentProcessingError(
            "Document is not a valid PDF file.",
            error_code=ERROR_PDF_TEXT_EXTRACTION_FAILED,
        )

    try:
        raw_segments, page_count, extractor_name = extract_pdf_page_segments_with_pymupdf(
            source_path=source_path,
        )
    except ModuleNotFoundError:
        logger.warning(
            "pymupdf is not installed; falling back to legacy pdf text extraction source_path=%s",
            source_path,
        )
        try:
            raw_segments, page_count, extractor_name = extract_pdf_page_segments_with_legacy_parser(
                raw_content,
            )
        except DocumentProcessingError:
            if not get_settings().enable_ocr:
                raise DocumentProcessingError(
                    "PDF text extraction failed and scanned PDF OCR is not enabled.",
                    error_code=ERROR_PDF_TEXT_EXTRACTION_FAILED,
                ) from None
            return extract_text_from_scanned_pdf(
                source_path=source_path,
                direct_error_code=ERROR_PDF_TEXT_EXTRACTION_FAILED,
            )
    except DocumentProcessingError:
        raise
    except Exception as exc:  # pragma: no cover - library error surface
        raise DocumentProcessingError(
            "PDF text extraction failed.",
            error_code=ERROR_PDF_TEXT_EXTRACTION_FAILED,
        ) from exc

    direct_text = "\n\n".join(sanitize_text(segment.text) for segment in raw_segments)
    quality = detect_text_quality(direct_text)
    if quality.status != TextQualityStatus.VALID:
        logger.info(
            "pdf direct text rejected source_path=%s extractor=%s page_count=%s quality=%s extracted_char_count=%s",
            source_path,
            extractor_name,
            page_count,
            quality.status.value,
            quality.character_count,
        )
        if not get_settings().enable_ocr:
            error_code = (
                ERROR_PDF_TEXT_GARBLED
                if quality.status in {
                    TextQualityStatus.GARBLED,
                    TextQualityStatus.BINARY_LIKE,
                }
                else ERROR_PDF_TEXT_EXTRACTION_FAILED
            )
            raise DocumentProcessingError(
                "This PDF does not contain enough readable text for PureLink Core. Scanned PDF OCR is not enabled.",
                error_code=error_code,
            )
        return extract_text_from_scanned_pdf(
            source_path=source_path,
            direct_error_code=(
                ERROR_PDF_TEXT_GARBLED
                if quality.status in {
                    TextQualityStatus.GARBLED,
                    TextQualityStatus.BINARY_LIKE,
                }
                else ERROR_PDF_TEXT_EXTRACTION_FAILED
            ),
        )

    logger.info(
        "pdf text extracted source_path=%s extractor=%s page_count=%s extracted_char_count=%s",
        source_path,
        extractor_name,
        page_count,
        quality.character_count,
    )

    return build_extracted_text_result(
        source_type="pdf",
        extractor=extractor_name,
        raw_segments=raw_segments,
        page_count=page_count,
    )


def extract_pdf_page_segments_with_pymupdf(
    *,
    source_path: Path,
) -> tuple[list[ExtractedTextSegment], int, str]:
    import fitz

    try:
        pdf_document = fitz.open(str(source_path))
    except Exception as exc:  # pragma: no cover - library error surface
        raise DocumentProcessingError(
            "PDF text extraction failed.",
            error_code=ERROR_PDF_TEXT_EXTRACTION_FAILED,
        ) from exc

    raw_segments: list[ExtractedTextSegment] = []
    try:
        page_count = pdf_document.page_count
        if page_count <= 0:
            raise DocumentProcessingError(
                "PDF document does not contain pages.",
                error_code=ERROR_PDF_TEXT_EXTRACTION_FAILED,
            )
        for page_index in range(page_count):
            page = pdf_document.load_page(page_index)
            page_number = page_index + 1
            raw_segments.append(
                ExtractedTextSegment(
                    text=page.get_text("text") or "",
                    metadata={
                        "source_type": "pdf",
                        "page_number": page_number,
                        "source_locator": f"page:{page_number}",
                        "extractor": "pymupdf",
                    },
                )
            )
    finally:
        pdf_document.close()

    return raw_segments, page_count, "pymupdf"


def extract_pdf_page_segments_with_legacy_parser(
    raw_content: bytes,
) -> tuple[list[ExtractedTextSegment], int, str]:
    page_texts = extract_pdf_page_texts(raw_content)
    raw_segments = [
        ExtractedTextSegment(
            text=text,
            metadata={
                "source_type": "pdf",
                "page_number": page_number,
                "source_locator": f"page:{page_number}",
                "extractor": "legacy_pdf_text",
            },
        )
        for page_number, text in enumerate(page_texts, start=1)
    ]
    return raw_segments, len(page_texts), "legacy_pdf_text"


def extract_text_from_scanned_pdf(
    *,
    source_path: Path,
    direct_error_code: str | None = None,
) -> ExtractedTextResult:
    with TemporaryDirectory(prefix="purelink-pdf-ocr-") as tmp_dir:
        try:
            rendered_pages = render_pdf_pages_to_images(
                source_path,
                output_dir=Path(tmp_dir),
            )
        except DocumentProcessingError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            raise DocumentProcessingError("PDF document could not be rendered for OCR.") from exc

        if not rendered_pages:
            raise DocumentProcessingError(
                "PDF document does not contain renderable pages for OCR.",
                error_code=direct_error_code or ERROR_PDF_TEXT_EXTRACTION_FAILED,
            )

        try:
            ocr_provider = resolve_ocr_provider()
        except OCRProviderError as exc:
            raise DocumentProcessingError(
                "OCR provider is not available for PDF fallback.",
                error_code=ERROR_OCR_PROVIDER_UNAVAILABLE,
            ) from exc

        raw_segments: list[ExtractedTextSegment] = []
        ocr_provider_name: str | None = None
        for rendered_page in rendered_pages:
            try:
                ocr_result = ocr_provider.extract_text(rendered_page.image_path)
            except OCRProviderError as exc:
                raise DocumentProcessingError(
                    str(exc),
                    error_code=ERROR_OCR_PROVIDER_UNAVAILABLE,
                ) from exc
            ocr_provider_name = ocr_result.provider_name
            raw_segments.extend(
                build_pdf_ocr_segments(
                    page_number=rendered_page.page_number,
                    ocr_result=ocr_result,
                )
            )
    try:
        result = build_extracted_text_result(
            source_type="pdf",
            extractor=f"ocr_pdf:{ocr_provider_name or 'unknown'}",
            raw_segments=raw_segments,
            page_count=len(rendered_pages),
        )
    except DocumentProcessingError as exc:
        if exc.error_code == ERROR_TEXT_QUALITY_TOO_LOW:
            raise DocumentProcessingError(
                "OCR did not find valid text in this PDF.",
                error_code=ERROR_OCR_NO_TEXT_FOUND,
            ) from exc
        raise

    logger.info(
        "pdf ocr fallback completed source_path=%s extractor=%s page_count=%s extracted_char_count=%s direct_error_code=%s",
        source_path,
        result.extractor,
        result.page_count,
        result.extracted_char_count,
        direct_error_code,
    )
    return result


def extract_text_from_docx(*, source_path: Path) -> ExtractedTextResult:
    if not source_path.exists():
        raise DocumentProcessingError("Document source file does not exist.")
    if not zipfile.is_zipfile(source_path):
        raise DocumentProcessingError("Document is not a valid DOCX file.")

    try:
        with zipfile.ZipFile(source_path) as archive:
            try:
                document_xml = archive.read("word/document.xml")
            except KeyError as exc:
                raise DocumentProcessingError("Document is not a valid DOCX file.") from exc

            styles_xml = archive.read("word/styles.xml") if "word/styles.xml" in archive.namelist() else None
    except OSError as exc:
        raise DocumentProcessingError("Document source file could not be read.") from exc

    styles_by_id = parse_docx_styles(styles_xml)
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise DocumentProcessingError("Document is not a valid DOCX file.") from exc

    current_section_title: str | None = None
    raw_segments: list[ExtractedTextSegment] = []
    for paragraph in root.findall(".//w:body/w:p", WORDPROCESSINGML_NS):
        paragraph_text = extract_docx_paragraph_text(paragraph)
        if not paragraph_text:
            continue

        style_id = extract_docx_paragraph_style_id(paragraph)
        style_name = styles_by_id.get(style_id or "", style_id or "")
        if is_docx_heading_style(style_id=style_id, style_name=style_name):
            current_section_title = paragraph_text
            raw_segments.append(
                ExtractedTextSegment(
                    text=paragraph_text,
                    metadata={
                        "source_type": "docx",
                        "section_title": current_section_title,
                    },
                )
            )
            continue

        metadata: dict[str, object] = {"source_type": "docx"}
        if current_section_title:
            metadata["section_title"] = current_section_title
        raw_segments.append(
            ExtractedTextSegment(
                text=paragraph_text,
                metadata=metadata,
            )
        )

    return build_extracted_text_result(
        source_type="docx",
        extractor="minimal_docx_text",
        raw_segments=raw_segments,
    )


def extract_text_from_image(*, source_path: Path) -> ExtractedTextResult:
    try:
        ocr_result = resolve_ocr_provider().extract_text(source_path)
    except OCRProviderError as exc:
        raise DocumentProcessingError(
            str(exc),
            error_code=ERROR_OCR_PROVIDER_UNAVAILABLE,
        ) from exc

    raw_segments = build_image_ocr_segments(ocr_result.regions, ocr_result=ocr_result)
    if not raw_segments:
        raw_segments = [
            ExtractedTextSegment(
                text=ocr_result.text,
                metadata={
                    "source_type": "image",
                    "source_locator": "image:ocr",
                    "ocr_provider": ocr_result.provider_name,
                    "ocr_provider_version": ocr_result.provider_version,
                    "ocr_language": ocr_result.language,
                    "region_count": len(ocr_result.regions),
                },
            )
        ]

    return build_extracted_text_result(
        source_type="image",
        extractor=f"ocr:{ocr_result.provider_name}",
        raw_segments=raw_segments,
    )


def extract_text_from_audio(*, source_path: Path) -> ExtractedTextResult:
    read_binary_file(source_path)
    try:
        asr_result = resolve_asr_provider().transcribe(source_path)
    except ASRProviderError as exc:
        raise DocumentProcessingError(str(exc)) from exc

    raw_segments = build_timed_transcript_segments(
        asr_result=asr_result,
        source_type="audio",
    )
    if not raw_segments:
        raw_segments = [
            ExtractedTextSegment(
                text=asr_result.full_text,
                metadata={
                    "source_type": "audio",
                    "asr_provider": asr_result.provider_name,
                    "asr_provider_version": asr_result.provider_version,
                },
            )
        ]

    return build_extracted_text_result(
        source_type="audio",
        extractor=f"asr:{asr_result.provider_name}",
        raw_segments=raw_segments,
    )


def extract_text_from_video(*, source_path: Path) -> ExtractedTextResult:
    read_binary_file(source_path)
    with TemporaryDirectory(prefix="purelink-video-audio-") as tmp_dir:
        extracted_audio_path = extract_audio_from_video(
            source_path=source_path,
            output_path=Path(tmp_dir) / "extracted-audio.wav",
        )
        try:
            asr_result = resolve_asr_provider().transcribe(extracted_audio_path)
        except ASRProviderError as exc:
            raise DocumentProcessingError(str(exc)) from exc

    raw_segments = build_timed_transcript_segments(
        asr_result=asr_result,
        source_type="video",
    )
    if not raw_segments:
        raw_segments = [
            ExtractedTextSegment(
                text=asr_result.full_text,
                metadata={
                    "source_type": "video",
                    "asr_provider": asr_result.provider_name,
                    "asr_provider_version": asr_result.provider_version,
                },
            )
        ]

    return build_extracted_text_result(
        source_type="video",
        extractor=f"video_asr:{asr_result.provider_name}",
        raw_segments=raw_segments,
    )


def read_text_file_with_fallback(source_path: Path) -> tuple[str, str]:
    raw_content = read_binary_file(source_path)
    decoded_text: str | None = None
    detected_encoding: str | None = None
    for candidate in TEXT_ENCODING_CANDIDATES:
        try:
            decoded_text = raw_content.decode(candidate)
            detected_encoding = candidate
            break
        except UnicodeDecodeError:
            continue

    if decoded_text is None or detected_encoding is None:
        raise DocumentProcessingError("Document could not be decoded as supported text.")

    if "\x00" in decoded_text:
        sanitized_quality = detect_text_quality(sanitize_text(decoded_text))
        if sanitized_quality.status != TextQualityStatus.VALID:
            raise DocumentProcessingError(
                "Document contains unsupported binary content.",
                error_code=ERROR_TEXT_QUALITY_TOO_LOW,
            )
    return decoded_text, detected_encoding


def read_binary_file(source_path: Path) -> bytes:
    if not source_path.exists():
        raise DocumentProcessingError("Document source file does not exist.")

    try:
        raw_content = source_path.read_bytes()
    except OSError as exc:
        raise DocumentProcessingError("Document source file could not be read.") from exc

    if not raw_content:
        raise DocumentProcessingError("Document source file is empty.")
    return raw_content


def build_extracted_text_result(
    *,
    source_type: str,
    extractor: str,
    raw_segments: list[ExtractedTextSegment],
    encoding: str | None = None,
    page_count: int | None = None,
) -> ExtractedTextResult:
    normalized_segments: list[ExtractedTextSegment] = []
    for segment in raw_segments:
        sanitized_text = sanitize_text(segment.text)
        quality = detect_text_quality(sanitized_text)
        if quality.status in {
            TextQualityStatus.EMPTY,
            TextQualityStatus.GARBLED,
            TextQualityStatus.BINARY_LIKE,
        }:
            continue
        normalized_text = normalize_extracted_text(quality.sanitized_text)
        if not normalized_text:
            continue
        metadata = {
            key: value
            for key, value in segment.metadata.items()
            if value is not None
        }
        metadata.setdefault("source_type", source_type)
        normalized_segments.append(
            ExtractedTextSegment(
                text=normalized_text,
                metadata=metadata,
            )
        )

    if not normalized_segments:
        raise DocumentProcessingError(
            "Document does not contain valid text content.",
            error_code=ERROR_TEXT_QUALITY_TOO_LOW,
        )

    combined_text = "\n\n".join(segment.text for segment in normalized_segments)
    combined_quality = detect_text_quality(combined_text)
    if combined_quality.status != TextQualityStatus.VALID:
        raise DocumentProcessingError(
            "Document does not contain valid text content.",
            error_code=ERROR_TEXT_QUALITY_TOO_LOW,
        )
    return ExtractedTextResult(
        text=combined_text,
        source_type=source_type,
        extractor=extractor,
        extracted_char_count=len(combined_text),
        segments=tuple(normalized_segments),
        encoding=encoding,
        page_count=page_count,
    )


def normalize_markdown_inline_text(text: str) -> str:
    normalized = text.strip()
    if normalized.startswith(">"):
        normalized = normalized.lstrip(">").strip()
    normalized = MARKDOWN_LIST_MARKER_PATTERN.sub("", normalized)
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", normalized)
    normalized = normalized.replace("`", "")
    normalized = MARKDOWN_EMPHASIS_PATTERN.sub("", normalized)
    return normalized


def normalize_extracted_text(text: str) -> str:
    normalized = sanitize_text(text)
    lines = normalized.split("\n")
    compact_lines: list[str] = []
    previous_blank = False

    for line in lines:
        compact = INLINE_WHITESPACE_PATTERN.sub(" ", line).strip()
        if not compact:
            if compact_lines and not previous_blank:
                compact_lines.append("")
            previous_blank = True
            continue

        compact_lines.append(compact)
        previous_blank = False

    return "\n".join(compact_lines).strip()


def build_image_ocr_segments(
    regions: tuple[OCRRegion, ...],
    *,
    ocr_result,
) -> list[ExtractedTextSegment]:
    if not regions:
        return []

    region_count = len(regions)
    segments: list[ExtractedTextSegment] = []
    for region in regions:
        normalized_region_text = normalize_extracted_text(region.text)
        if not normalized_region_text:
            continue

        region_payload = {
            "left": region.left,
            "top": region.top,
            "width": region.width,
            "height": region.height,
        }
        if region.confidence is not None:
            region_payload["confidence"] = round(region.confidence, 3)

        segments.append(
            ExtractedTextSegment(
                text=normalized_region_text,
                metadata={
                    "source_type": "image",
                    "source_locator": "image:ocr",
                    "ocr_provider": ocr_result.provider_name,
                    "ocr_provider_version": ocr_result.provider_version,
                    "ocr_language": ocr_result.language,
                    "region_count": region_count,
                    "region": region_payload,
                },
            )
        )
    return segments


def build_pdf_ocr_segments(
    *,
    page_number: int,
    ocr_result,
) -> list[ExtractedTextSegment]:
    locator = f"page:{page_number}"
    if not ocr_result.regions:
        return [
            ExtractedTextSegment(
                text=ocr_result.text,
                metadata={
                    "source_type": "pdf",
                    "page_number": page_number,
                    "source_locator": locator,
                    "extractor": f"ocr_pdf:{ocr_result.provider_name}",
                    "ocr_provider": ocr_result.provider_name,
                    "ocr_provider_version": ocr_result.provider_version,
                    "ocr_language": ocr_result.language,
                    "region_count": len(ocr_result.regions),
                },
            )
        ]

    region_count = len(ocr_result.regions)
    segments: list[ExtractedTextSegment] = []
    for region in ocr_result.regions:
        normalized_region_text = normalize_extracted_text(region.text)
        if not normalized_region_text:
            continue

        region_payload = {
            "left": region.left,
            "top": region.top,
            "width": region.width,
            "height": region.height,
        }
        if region.confidence is not None:
            region_payload["confidence"] = round(region.confidence, 3)

        segments.append(
            ExtractedTextSegment(
                text=normalized_region_text,
                metadata={
                    "source_type": "pdf",
                    "page_number": page_number,
                    "source_locator": locator,
                    "extractor": f"ocr_pdf:{ocr_result.provider_name}",
                    "ocr_provider": ocr_result.provider_name,
                    "ocr_provider_version": ocr_result.provider_version,
                    "ocr_language": ocr_result.language,
                    "region_count": region_count,
                    "region": region_payload,
                },
            )
        )
    if segments:
        return segments

    return [
        ExtractedTextSegment(
            text=ocr_result.text,
            metadata={
                "source_type": "pdf",
                "page_number": page_number,
                "source_locator": locator,
                "extractor": f"ocr_pdf:{ocr_result.provider_name}",
                "ocr_provider": ocr_result.provider_name,
                "ocr_provider_version": ocr_result.provider_version,
                "ocr_language": ocr_result.language,
                "region_count": region_count,
            },
        )
    ]


def build_timed_transcript_segments(
    *,
    asr_result,
    source_type: str,
) -> list[ExtractedTextSegment]:
    segments: list[ExtractedTextSegment] = []
    for segment in asr_result.segments:
        normalized_text = normalize_extracted_text(segment.text)
        if not normalized_text:
            continue
        segments.append(
            ExtractedTextSegment(
                text=normalized_text,
                metadata={
                    "source_type": source_type,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "asr_provider": asr_result.provider_name,
                    "asr_provider_version": asr_result.provider_version,
                },
            )
        )
    return segments


def chunk_extracted_text_result(
    *,
    extracted: ExtractedTextResult,
    document_id: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    direct_chunk_threshold: int = DIRECT_CHUNK_THRESHOLD,
) -> list[GeneratedChunkPayload]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between zero and chunk_size - 1.")

    prepared_segments = build_prepared_segments(extracted.segments)
    if not prepared_segments:
        raise DocumentProcessingError("Document does not contain valid text content.")

    total_length = prepared_segments[-1].char_end
    if total_length <= direct_chunk_threshold and not should_preserve_source_boundaries(
        prepared_segments
    ):
        chunk_text = "\n\n".join(segment.text for segment in prepared_segments)
        chunk_metadata = build_chunk_metadata(
            prepared_segments=prepared_segments,
            char_start=0,
            char_end=total_length,
        )
        return [
            build_generated_chunk(
                document_id=document_id,
                chunk_index=0,
                chunk_text=chunk_text,
                metadata=chunk_metadata,
            )
        ]

    chunks: list[GeneratedChunkPayload] = []
    current_segments: list[PreparedTextSegment] = []
    current_length = 0
    chunk_index = 0

    for segment in prepared_segments:
        segment_length = len(segment.text)
        if segment_length > chunk_size:
            if current_segments:
                chunks.append(
                    build_chunk_from_segments(
                        document_id=document_id,
                        chunk_index=chunk_index,
                        prepared_segments=current_segments,
                    )
                )
                chunk_index += 1
                current_segments = []
                current_length = 0

            split_chunks = split_large_segment_into_chunks(
                document_id=document_id,
                chunk_index_start=chunk_index,
                segment=segment,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            chunks.extend(split_chunks)
            chunk_index += len(split_chunks)
            continue

        if current_segments and should_start_new_chunk_for_segment(
            current_segments=current_segments,
            next_segment=segment,
        ):
            chunks.append(
                build_chunk_from_segments(
                    document_id=document_id,
                    chunk_index=chunk_index,
                    prepared_segments=current_segments,
                )
            )
            chunk_index += 1
            current_segments = []
            current_length = 0

        separator_length = 0 if not current_segments else 2
        if current_length + separator_length + segment_length <= chunk_size:
            current_segments.append(segment)
            current_length += separator_length + segment_length
            continue

        chunks.append(
            build_chunk_from_segments(
                document_id=document_id,
                chunk_index=chunk_index,
                prepared_segments=current_segments,
            )
        )
        chunk_index += 1
        current_segments = [segment]
        current_length = segment_length

    if current_segments:
        chunks.append(
            build_chunk_from_segments(
                document_id=document_id,
                chunk_index=chunk_index,
                prepared_segments=current_segments,
            )
        )

    if not chunks:
        raise DocumentProcessingError("Document does not contain valid text content.")
    return chunks


def chunk_text_content(
    *,
    text: str,
    document_id: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    direct_chunk_threshold: int = DIRECT_CHUNK_THRESHOLD,
) -> list[GeneratedChunkPayload]:
    extracted = build_extracted_text_result(
        source_type="text",
        extractor="text",
        raw_segments=[
            ExtractedTextSegment(
                text=text,
                metadata={"source_type": "text"},
            )
        ],
    )
    return chunk_extracted_text_result(
        extracted=extracted,
        document_id=document_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        direct_chunk_threshold=direct_chunk_threshold,
    )


def build_prepared_segments(
    segments: tuple[ExtractedTextSegment, ...],
) -> list[PreparedTextSegment]:
    prepared_segments: list[PreparedTextSegment] = []
    char_cursor = 0
    for segment in segments:
        prepared_segments.append(
            PreparedTextSegment(
                text=segment.text,
                metadata=segment.metadata,
                char_start=char_cursor,
                char_end=char_cursor + len(segment.text),
            )
        )
        char_cursor += len(segment.text) + 2
    return prepared_segments


def build_chunk_from_segments(
    *,
    document_id: int,
    chunk_index: int,
    prepared_segments: list[PreparedTextSegment],
) -> GeneratedChunkPayload:
    chunk_text = "\n\n".join(segment.text for segment in prepared_segments)
    char_start = prepared_segments[0].char_start
    char_end = prepared_segments[-1].char_end
    metadata = build_chunk_metadata(
        prepared_segments=prepared_segments,
        char_start=char_start,
        char_end=char_end,
    )
    return build_generated_chunk(
        document_id=document_id,
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        metadata=metadata,
    )


def split_large_segment_into_chunks(
    *,
    document_id: int,
    chunk_index_start: int,
    segment: PreparedTextSegment,
    chunk_size: int,
    chunk_overlap: int,
) -> list[GeneratedChunkPayload]:
    chunk_payloads: list[GeneratedChunkPayload] = []
    local_start = 0
    chunk_index = chunk_index_start
    while local_start < len(segment.text):
        max_end = min(len(segment.text), local_start + chunk_size)
        local_end = _resolve_chunk_end(
            text=segment.text,
            start=local_start,
            max_end=max_end,
            chunk_size=chunk_size,
        )
        chunk_text = segment.text[local_start:local_end].strip()
        if chunk_text:
            metadata = build_chunk_metadata(
                prepared_segments=[segment],
                char_start=segment.char_start + local_start,
                char_end=segment.char_start + local_end,
            )
            chunk_payloads.append(
                build_generated_chunk(
                    document_id=document_id,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    metadata=metadata,
                )
            )
            chunk_index += 1

        if local_end >= len(segment.text):
            break

        next_start = max(local_end - chunk_overlap, local_start + 1)
        while next_start < len(segment.text) and segment.text[next_start].isspace():
            next_start += 1
        local_start = next_start

    return chunk_payloads


def build_generated_chunk(
    *,
    document_id: int,
    chunk_index: int,
    chunk_text: str,
    metadata: dict[str, object] | None = None,
) -> GeneratedChunkPayload:
    metadata_json = None
    if metadata:
        metadata_json = json.dumps(
            _normalize_chunk_metadata_for_storage(
                metadata,
                chunk_index=chunk_index,
            ),
            ensure_ascii=False,
        )
    return GeneratedChunkPayload(
        chunk_key=f"{document_id}:{chunk_index}",
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        metadata_json=metadata_json,
    )


def _normalize_chunk_metadata_for_storage(
    metadata: dict[str, object],
    *,
    chunk_index: int,
) -> dict[str, object]:
    payload = dict(metadata)
    raw_source_type = payload.get("source_type")
    source_type = normalize_source_type(raw_source_type if isinstance(raw_source_type, str) else None)
    if source_type:
        payload["source_type"] = source_type

    if source_type == "text":
        payload["extractor"] = str(payload.get("extractor") or "text")
        payload["source_locator"] = f"text:chunk:{chunk_index}"
        return payload

    if source_type == "markdown":
        payload["extractor"] = str(payload.get("extractor") or "markdown")
        heading = _resolve_chunk_heading(payload)
        payload["source_locator"] = (
            f"heading:{heading}"
            if heading
            else f"markdown:chunk:{chunk_index}"
        )
        return payload

    if source_type == "pdf" and isinstance(payload.get("page_number"), int):
        payload["source_locator"] = f"page:{payload['page_number']}"

    return payload


def _resolve_chunk_heading(metadata: dict[str, object]) -> str | None:
    heading_path = metadata.get("heading_path")
    if isinstance(heading_path, list):
        for item in heading_path:
            if isinstance(item, str) and item.strip():
                return item.strip()

    section_title = metadata.get("section_title")
    if isinstance(section_title, str) and section_title.strip():
        return section_title.strip()
    return None


def should_fallback_to_pdf_ocr(page_texts: list[str]) -> bool:
    if not page_texts:
        return True

    normalized_pages = [
        normalize_extracted_text(page_text)
        for page_text in page_texts
    ]
    combined_text = "\n".join(
        page_text
        for page_text in normalized_pages
        if page_text
    ).strip()
    if not combined_text:
        return True

    meaningful_char_count = sum(
        1
        for character in combined_text
        if character.isalnum()
    )
    word_count = len(
        [
            token
            for token in re.split(r"\s+", combined_text)
            if any(character.isalnum() for character in token)
        ]
    )
    return meaningful_char_count < PDF_OCR_FALLBACK_MIN_CHARS and word_count < 4


def render_pdf_pages_to_images(
    source_path: Path,
    *,
    output_dir: Path,
) -> list[RenderedPDFPage]:
    try:
        import pypdfium2 as pdfium
    except ModuleNotFoundError as exc:
        raise DocumentProcessingError("PDF OCR rendering dependency is not installed.") from exc

    try:
        pdf_document = pdfium.PdfDocument(str(source_path))
    except Exception as exc:  # pragma: no cover - library error surface
        raise DocumentProcessingError("PDF document could not be rendered for OCR.") from exc

    rendered_pages: list[RenderedPDFPage] = []
    try:
        page_count = len(pdf_document)
        for page_index in range(page_count):
            page = pdf_document[page_index]
            try:
                pil_image = page.render(scale=PDF_OCR_RENDER_SCALE).to_pil()
            except Exception as exc:  # pragma: no cover - library error surface
                raise DocumentProcessingError(
                    f"PDF page {page_index + 1} could not be rendered for OCR."
                ) from exc
            finally:
                page.close()

            image_path = output_dir / f"page-{page_index + 1}.png"
            pil_image.save(image_path, format="PNG")
            pil_image.close()
            rendered_pages.append(
                RenderedPDFPage(
                    page_number=page_index + 1,
                    image_path=image_path,
                )
            )
        return rendered_pages
    finally:
        pdf_document.close()


def extract_audio_from_video(
    *,
    source_path: Path,
    output_path: Path,
) -> Path:
    ffmpeg_command = get_settings().asr_ffmpeg_command
    try:
        completed = subprocess.run(
            [
                ffmpeg_command,
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(DEFAULT_ASR_SAMPLE_RATE),
                "-f",
                "wav",
                str(output_path),
            ],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise DocumentProcessingError("Video audio extraction tool is not available.") from exc

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Video audio track could not be extracted."
        )
        raise DocumentProcessingError(message)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise DocumentProcessingError("Video audio track could not be extracted.")
    return output_path


def should_preserve_source_boundaries(
    prepared_segments: list[PreparedTextSegment],
) -> bool:
    page_numbers = {
        int(segment.metadata["page_number"])
        for segment in prepared_segments
        if segment.metadata.get("source_type") == "pdf"
        and isinstance(segment.metadata.get("page_number"), int)
    }
    if len(page_numbers) > 1:
        return True

    timed_ranges = {
        (
            float(segment.metadata["start_time"]),
            float(segment.metadata["end_time"]),
        )
        for segment in prepared_segments
        if segment.metadata.get("source_type") in TIMED_TRANSCRIPT_SOURCE_TYPES
        and isinstance(segment.metadata.get("start_time"), (int, float))
        and isinstance(segment.metadata.get("end_time"), (int, float))
    }
    return len(timed_ranges) > 1


def should_start_new_chunk_for_segment(
    *,
    current_segments: list[PreparedTextSegment],
    next_segment: PreparedTextSegment,
) -> bool:
    next_page_number = next_segment.metadata.get("page_number")
    if next_segment.metadata.get("source_type") != "pdf" or not isinstance(next_page_number, int):
        next_start_time = next_segment.metadata.get("start_time")
        next_end_time = next_segment.metadata.get("end_time")
        if (
            next_segment.metadata.get("source_type") not in TIMED_TRANSCRIPT_SOURCE_TYPES
            or not isinstance(next_start_time, (int, float))
            or not isinstance(next_end_time, (int, float))
        ):
            return False

        current_timed_ranges = {
            (
                float(segment.metadata["start_time"]),
                float(segment.metadata["end_time"]),
            )
            for segment in current_segments
            if segment.metadata.get("source_type") in TIMED_TRANSCRIPT_SOURCE_TYPES
            and isinstance(segment.metadata.get("start_time"), (int, float))
            and isinstance(segment.metadata.get("end_time"), (int, float))
        }
        return len(current_timed_ranges) == 1 and (
            float(next_start_time),
            float(next_end_time),
        ) not in current_timed_ranges

    current_page_numbers = {
        int(segment.metadata["page_number"])
        for segment in current_segments
        if segment.metadata.get("source_type") == "pdf"
        and isinstance(segment.metadata.get("page_number"), int)
    }
    return len(current_page_numbers) == 1 and next_page_number not in current_page_numbers


def build_chunk_metadata(
    *,
    prepared_segments: list[PreparedTextSegment],
    char_start: int,
    char_end: int,
) -> dict[str, object]:
    source_types = {
        str(segment.metadata.get("source_type"))
        for segment in prepared_segments
        if segment.metadata.get("source_type")
    }
    source_type = source_types.pop() if len(source_types) == 1 else "text"

    page_numbers = {
        int(segment.metadata["page_number"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("page_number"), int)
    }
    page_number = page_numbers.pop() if len(page_numbers) == 1 else None

    start_times = [
        float(segment.metadata["start_time"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("start_time"), (int, float))
    ]
    end_times = [
        float(segment.metadata["end_time"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("end_time"), (int, float))
    ]
    start_time = min(start_times) if start_times else None
    end_time = max(end_times) if end_times else None

    section_titles = {
        str(segment.metadata["section_title"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("section_title"), str)
        and str(segment.metadata["section_title"]).strip()
    }
    section_title = section_titles.pop() if len(section_titles) == 1 else None

    source_locators = {
        str(segment.metadata["source_locator"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("source_locator"), str)
        and str(segment.metadata["source_locator"]).strip()
    }
    source_locator = source_locators.pop() if len(source_locators) == 1 else None

    heading_paths = {
        tuple(segment.metadata["heading_path"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("heading_path"), list)
        and all(isinstance(item, str) and item.strip() for item in segment.metadata["heading_path"])
    }
    heading_path = heading_paths.pop() if len(heading_paths) == 1 else None

    ocr_providers = {
        str(segment.metadata["ocr_provider"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("ocr_provider"), str)
        and str(segment.metadata["ocr_provider"]).strip()
    }
    ocr_provider = ocr_providers.pop() if len(ocr_providers) == 1 else None

    ocr_provider_versions = {
        str(segment.metadata["ocr_provider_version"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("ocr_provider_version"), str)
        and str(segment.metadata["ocr_provider_version"]).strip()
    }
    ocr_provider_version = (
        ocr_provider_versions.pop()
        if len(ocr_provider_versions) == 1
        else None
    )

    ocr_languages = {
        str(segment.metadata["ocr_language"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("ocr_language"), str)
        and str(segment.metadata["ocr_language"]).strip()
    }
    ocr_language = ocr_languages.pop() if len(ocr_languages) == 1 else None

    extractors = {
        str(segment.metadata["extractor"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("extractor"), str)
        and str(segment.metadata["extractor"]).strip()
    }
    extractor = extractors.pop() if len(extractors) == 1 else None

    asr_providers = {
        str(segment.metadata["asr_provider"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("asr_provider"), str)
        and str(segment.metadata["asr_provider"]).strip()
    }
    asr_provider = asr_providers.pop() if len(asr_providers) == 1 else None

    asr_provider_versions = {
        str(segment.metadata["asr_provider_version"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("asr_provider_version"), str)
        and str(segment.metadata["asr_provider_version"]).strip()
    }
    asr_provider_version = (
        asr_provider_versions.pop()
        if len(asr_provider_versions) == 1
        else None
    )

    region_counts = {
        int(segment.metadata["region_count"])
        for segment in prepared_segments
        if isinstance(segment.metadata.get("region_count"), int)
    }
    regions = [
        {
            key: value
            for key, value in segment.metadata["region"].items()
            if isinstance(key, str)
        }
        for segment in prepared_segments
        if isinstance(segment.metadata.get("region"), dict)
    ]
    region_count = len(regions) if regions else (
        region_counts.pop()
        if len(region_counts) == 1
        else None
    )

    return build_chunk_metadata_payload(
        source_type=source_type,
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        start_time=start_time,
        end_time=end_time,
        section_title=section_title,
        source_locator=source_locator,
        heading_path=heading_path,
        ocr_provider=ocr_provider,
        ocr_provider_version=ocr_provider_version,
        ocr_language=ocr_language,
        extractor=extractor,
        asr_provider=asr_provider,
        asr_provider_version=asr_provider_version,
        region_count=region_count,
        regions=regions or None,
    )


def build_citation_unit_payloads(
    *,
    chunks: list[GeneratedChunkPayload],
    document: Document,
) -> list[GeneratedCitationUnitPayload]:
    settings = get_settings()
    generated_units: list[GeneratedCitationUnitPayload] = []
    unit_index = 0

    for chunk in chunks:
        chunk_metadata = parse_chunk_metadata_json(chunk.metadata_json)
        chunk_units = build_citation_units_for_chunk(
            chunk=chunk,
            chunk_metadata=chunk_metadata,
            min_chars=settings.citation_unit_min_chars,
            target_chars=settings.citation_unit_target_chars,
            max_chars=settings.citation_unit_max_chars,
            max_sentences=settings.citation_unit_max_sentences,
        )
        for unit in chunk_units:
            generated_units.append(
                GeneratedCitationUnitPayload(
                    chunk_key=chunk.chunk_key,
                    unit_index=unit_index,
                    unit_text=unit.unit_text,
                    start_char=unit.start_char,
                    end_char=unit.end_char,
                    metadata_json=unit.metadata_json,
                )
            )
            unit_index += 1

    return generated_units


def parse_chunk_metadata_json(metadata_json: str | None) -> dict[str, object]:
    if not metadata_json:
        return {}
    try:
        payload = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_citation_units_for_chunk(
    *,
    chunk: GeneratedChunkPayload,
    chunk_metadata: dict[str, object],
    min_chars: int,
    target_chars: int,
    max_chars: int,
    max_sentences: int,
) -> list[GeneratedCitationUnitPayload]:
    sentence_spans = [
        span
        for span in expand_sentence_spans_for_citation_units(
            split_text_into_sentence_spans(chunk.chunk_text),
            max_chars=max_chars,
        )
        if not is_low_value_sentence_span(span.text, chunk_metadata=chunk_metadata)
    ]
    if not sentence_spans:
        return []

    chunk_char_start = (
        int(chunk_metadata["char_start"])
        if isinstance(chunk_metadata.get("char_start"), int)
        else None
    )
    units: list[GeneratedCitationUnitPayload] = []
    local_unit_index = 0
    cursor = 0
    while cursor < len(sentence_spans):
        merged_spans = [sentence_spans[cursor]]
        merged_text = normalize_citation_unit_text(merged_spans[0].text)

        while (
            cursor + len(merged_spans) < len(sentence_spans)
            and len(merged_spans) < max_sentences
            and len(merged_text) < target_chars
        ):
            next_span = sentence_spans[cursor + len(merged_spans)]
            candidate_text = normalize_citation_unit_text(
                " ".join(span.text for span in [*merged_spans, next_span])
            )
            if len(candidate_text) > max_chars:
                break
            merged_spans.append(next_span)
            merged_text = candidate_text
            if len(merged_text) >= min_chars:
                break

        if len(merged_text) < min_chars and cursor + len(merged_spans) < len(sentence_spans):
            next_span = sentence_spans[cursor + len(merged_spans)]
            candidate_text = normalize_citation_unit_text(
                " ".join(span.text for span in [*merged_spans, next_span])
            )
            if len(candidate_text) <= max_chars and len(merged_spans) < max_sentences:
                merged_spans.append(next_span)
                merged_text = candidate_text

        if not merged_text or is_low_value_sentence_span(merged_text, chunk_metadata=chunk_metadata):
            cursor += max(1, len(merged_spans))
            continue

        unit_char_start = merged_spans[0].start_char
        unit_char_end = merged_spans[-1].end_char
        metadata = dict(chunk_metadata)
        metadata["parent_chunk_index"] = chunk.chunk_index
        metadata["char_start"] = (
            chunk_char_start + unit_char_start if chunk_char_start is not None else unit_char_start
        )
        metadata["char_end"] = (
            chunk_char_start + unit_char_end if chunk_char_start is not None else unit_char_end
        )
        metadata["source_locator"] = build_source_locator(
            source_type=str(metadata.get("source_type")) if isinstance(metadata.get("source_type"), str) else None,
            char_start=metadata["char_start"] if isinstance(metadata["char_start"], int) else None,
            char_end=metadata["char_end"] if isinstance(metadata["char_end"], int) else None,
            page_number=int(metadata["page_number"]) if isinstance(metadata.get("page_number"), int) else None,
            start_time=float(metadata["start_time"]) if isinstance(metadata.get("start_time"), (int, float)) else None,
            end_time=float(metadata["end_time"]) if isinstance(metadata.get("end_time"), (int, float)) else None,
            section_title=str(metadata["section_title"]) if isinstance(metadata.get("section_title"), str) else None,
        )
        units.append(
            GeneratedCitationUnitPayload(
                chunk_key=chunk.chunk_key,
                unit_index=local_unit_index,
                unit_text=merged_text,
                start_char=metadata["char_start"] if isinstance(metadata["char_start"], int) else None,
                end_char=metadata["char_end"] if isinstance(metadata["char_end"], int) else None,
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
        )
        local_unit_index += 1
        cursor += max(1, len(merged_spans))

    return units


def expand_sentence_spans_for_citation_units(
    sentence_spans: list[SentenceSpan],
    *,
    max_chars: int,
) -> list[SentenceSpan]:
    expanded: list[SentenceSpan] = []
    for span in sentence_spans:
        expanded.extend(split_oversized_sentence_span(span, max_chars=max_chars))
    return expanded


def split_oversized_sentence_span(
    span: SentenceSpan,
    *,
    max_chars: int,
) -> list[SentenceSpan]:
    normalized = normalize_citation_unit_text(span.text)
    if len(normalized) <= max_chars:
        return [span]

    clause_spans = split_text_into_clause_spans(span.text, base_start=span.start_char)
    if len(clause_spans) <= 1:
        return [span]

    merged_spans: list[SentenceSpan] = []
    cursor = 0
    while cursor < len(clause_spans):
        current = clause_spans[cursor]
        current_text = normalize_citation_unit_text(current.text)
        next_index = cursor + 1

        while next_index < len(clause_spans):
            candidate = clause_spans[next_index]
            candidate_text = normalize_citation_unit_text(f"{current_text} {candidate.text}")
            if len(candidate_text) > max_chars:
                break
            current = SentenceSpan(
                text=span.text[current.start_char - span.start_char:candidate.end_char - span.start_char],
                start_char=current.start_char,
                end_char=candidate.end_char,
            )
            current_text = candidate_text
            next_index += 1

        merged_spans.append(
            SentenceSpan(
                text=normalize_citation_unit_text(current.text),
                start_char=current.start_char,
                end_char=current.end_char,
            )
        )
        cursor = next_index

    return merged_spans or [span]


def split_text_into_clause_spans(text: str, *, base_start: int = 0) -> list[SentenceSpan]:
    spans: list[SentenceSpan] = []
    start = 0
    text_length = len(text)

    def flush(raw_start: int, raw_end: int) -> None:
        trimmed_start = raw_start
        trimmed_end = raw_end
        while trimmed_start < trimmed_end and text[trimmed_start].isspace():
            trimmed_start += 1
        while trimmed_end > trimmed_start and text[trimmed_end - 1].isspace():
            trimmed_end -= 1
        if trimmed_start >= trimmed_end:
            return
        spans.append(
            SentenceSpan(
                text=text[trimmed_start:trimmed_end],
                start_char=base_start + trimmed_start,
                end_char=base_start + trimmed_end,
            )
        )

    for index, character in enumerate(text):
        if character in CLAUSE_ENDING_CHARACTERS:
            flush(start, index + 1)
            start = index + 1
    flush(start, text_length)
    return spans


def split_text_into_sentence_spans(text: str) -> list[SentenceSpan]:
    spans: list[SentenceSpan] = []
    start = 0
    index = 0
    text_length = len(text)

    def flush(raw_start: int, raw_end: int) -> None:
        trimmed_start = raw_start
        trimmed_end = raw_end
        while trimmed_start < trimmed_end and text[trimmed_start].isspace():
            trimmed_start += 1
        while trimmed_end > trimmed_start and text[trimmed_end - 1].isspace():
            trimmed_end -= 1
        if trimmed_start >= trimmed_end:
            return
        snippet = text[trimmed_start:trimmed_end]
        spans.append(
            SentenceSpan(
                text=snippet,
                start_char=trimmed_start,
                end_char=trimmed_end,
            )
        )

    while index < text_length:
        character = text[index]
        if character in SENTENCE_ENDING_CHARACTERS:
            flush(start, index + 1)
            start = index + 1
        elif character == "\n":
            newline_start = index
            while index < text_length and text[index] == "\n":
                index += 1
            if index - newline_start >= 2:
                flush(start, newline_start)
                start = index
            continue
        index += 1

    flush(start, text_length)
    return spans


def normalize_citation_unit_text(text: str) -> str:
    return " ".join(text.split()).strip()


def is_low_value_sentence_span(
    text: str,
    *,
    chunk_metadata: dict[str, object],
) -> bool:
    normalized = normalize_citation_unit_text(text)
    if not normalized:
        return True
    if normalized in LOW_VALUE_CITATION_TEXTS:
        return True
    if len(normalized) < 6 and not any(character.isalnum() for character in normalized):
        return True
    if len(normalized) < 8 and sum(character.isalnum() for character in normalized) < 3:
        return True
    if all(not character.isalnum() for character in normalized):
        return True

    section_title = chunk_metadata.get("section_title")
    if isinstance(section_title, str) and normalize_citation_unit_text(section_title) == normalized:
        return True

    heading_path = chunk_metadata.get("heading_path")
    if isinstance(heading_path, list):
        for item in heading_path:
            if isinstance(item, str) and normalize_citation_unit_text(item) == normalized:
                return True

    if normalized.endswith("...") and len(normalized) < 16:
        return True
    return False


def replace_document_chunks(
    db: Session,
    *,
    document: Document,
    chunks: list[GeneratedChunkPayload],
    citation_units: list[GeneratedCitationUnitPayload] | None = None,
) -> list[DocumentChunk]:
    validate_generated_chunks(chunks)
    db.execute(delete(DocumentCitationUnit).where(DocumentCitationUnit.document_id == document.id))
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    now = datetime.now(UTC)
    saved_chunks: list[DocumentChunk] = []
    for item in chunks:
        saved_chunk = DocumentChunk(
            document_id=document.id,
            chunk_key=item.chunk_key,
            chunk_index=item.chunk_index,
            chunk_text=item.chunk_text,
            metadata_json=item.metadata_json,
            created_at=now,
            updated_at=now,
        )
        db.add(saved_chunk)
        saved_chunks.append(saved_chunk)
    db.flush()

    chunk_lookup = {item.chunk_key: item for item in saved_chunks}
    for item in citation_units or []:
        parent_chunk = chunk_lookup.get(item.chunk_key)
        if parent_chunk is None:
            raise DocumentProcessingError(
                "Citation unit parent chunk is missing.",
                error_code=ERROR_CHUNK_PERSIST_FAILED,
            )
        db.add(
            DocumentCitationUnit(
                document_id=document.id,
                chunk_id=parent_chunk.id,
                knowledge_base_id=document.knowledge_base_id,
                chunk_key=item.chunk_key,
                unit_index=item.unit_index,
                unit_text=item.unit_text,
                start_char=item.start_char,
                end_char=item.end_char,
                metadata_json=item.metadata_json,
                created_at=now,
                updated_at=now,
            )
        )
    return saved_chunks


def validate_generated_chunks(chunks: list[GeneratedChunkPayload]) -> None:
    if not chunks:
        raise DocumentProcessingError(
            "Document did not produce any valid chunks.",
            error_code=ERROR_TEXT_QUALITY_TOO_LOW,
        )

    for item in chunks:
        quality = detect_text_quality(item.chunk_text)
        if "\x00" in item.chunk_text or quality.status != TextQualityStatus.VALID:
            raise DocumentProcessingError(
                "Chunk text quality is too low to save.",
                error_code=ERROR_TEXT_QUALITY_TOO_LOW,
            )


def validate_generated_citation_units(citation_units: list[GeneratedCitationUnitPayload]) -> None:
    for item in citation_units:
        quality = detect_text_quality(item.unit_text)
        if "\x00" in item.unit_text or quality.status in {
            TextQualityStatus.EMPTY,
            TextQualityStatus.GARBLED,
            TextQualityStatus.BINARY_LIKE,
        }:
            raise DocumentProcessingError(
                "Citation unit text quality is too low to save.",
                error_code=ERROR_TEXT_QUALITY_TOO_LOW,
            )


def filter_generated_citation_units(
    *,
    citation_units: list[GeneratedCitationUnitPayload],
    document_id: int,
    knowledge_base_id: int,
) -> list[GeneratedCitationUnitPayload]:
    valid_units: list[GeneratedCitationUnitPayload] = []
    dropped_count = 0

    for item in citation_units:
        quality = detect_text_quality(item.unit_text)
        if "\x00" in item.unit_text or quality.status in {
            TextQualityStatus.EMPTY,
            TextQualityStatus.GARBLED,
            TextQualityStatus.BINARY_LIKE,
        }:
            dropped_count += 1
            continue
        valid_units.append(item)

    if dropped_count:
        logger.warning(
            "dropped low-quality citation units document_id=%s knowledge_base_id=%s dropped_count=%s kept_count=%s",
            document_id,
            knowledge_base_id,
            dropped_count,
            len(valid_units),
        )

    return valid_units


def extract_pdf_page_texts(raw_content: bytes) -> list[str]:
    objects = parse_pdf_objects(raw_content)
    page_object_bodies = [
        body
        for _, body in sorted(objects.items())
        if PDF_PAGE_TYPE_PATTERN.search(body) and not PDF_PAGES_TYPE_PATTERN.search(body)
    ]
    page_texts: list[str] = []

    for body in page_object_bodies:
        content_object_ids = extract_pdf_content_object_ids(body)
        page_fragments: list[str] = []
        for object_id in content_object_ids:
            stream_body = objects.get(object_id)
            if stream_body is None:
                continue
            decoded_stream = decode_pdf_stream_body(stream_body)
            if decoded_stream is None:
                continue
            page_fragments.append(extract_text_from_pdf_stream(decoded_stream))

        page_text = "\n".join(fragment for fragment in page_fragments if fragment).strip()
        if page_text:
            page_texts.append(page_text)

    if not page_texts:
        raise DocumentProcessingError("PDF document does not contain extractable text.")
    return page_texts


def parse_pdf_objects(raw_content: bytes) -> dict[int, bytes]:
    objects: dict[int, bytes] = {}
    for match in PDF_OBJECT_PATTERN.finditer(raw_content):
        object_id = int(match.group(1))
        objects[object_id] = match.group(2)
    if not objects:
        raise DocumentProcessingError("Document is not a valid PDF file.")
    return objects


def extract_pdf_content_object_ids(page_body: bytes) -> list[int]:
    array_match = PDF_CONTENTS_ARRAY_PATTERN.search(page_body)
    if array_match is not None:
        return [int(item) for item in PDF_CONTENT_REF_PATTERN.findall(array_match.group(1))]

    single_match = PDF_CONTENTS_SINGLE_PATTERN.search(page_body)
    if single_match is not None:
        return [int(single_match.group(1))]
    return []


def decode_pdf_stream_body(object_body: bytes) -> bytes | None:
    stream_match = PDF_STREAM_PATTERN.search(object_body)
    if stream_match is None:
        return None

    stream_bytes = stream_match.group(1)
    if b"/FlateDecode" in object_body:
        try:
            return zlib.decompress(stream_bytes)
        except zlib.error:
            return None
    return stream_bytes


def extract_text_from_pdf_stream(stream_bytes: bytes) -> str:
    text_blocks = PDF_BT_ET_PATTERN.findall(stream_bytes)
    if not text_blocks:
        text_blocks = [stream_bytes]

    extracted_lines: list[str] = []
    for block in text_blocks:
        fragments: list[str] = []
        for array_match in re.finditer(rb"\[(.*?)\]\s*TJ", block, re.S):
            fragments.extend(extract_pdf_text_fragments(array_match.group(1)))
        for literal_match in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*(?:Tj|'|\")", block):
            fragments.append(decode_pdf_literal_string(literal_match.group(0).split(b")", maxsplit=1)[0] + b")"))
        for hex_match in re.finditer(rb"<([0-9A-Fa-f\s]+)>\s*(?:Tj|'|\")", block):
            fragments.append(decode_pdf_hex_string(hex_match.group(1)))

        line = " ".join(fragment.strip() for fragment in fragments if fragment.strip()).strip()
        if line:
            extracted_lines.append(line)

    return "\n".join(extracted_lines)


def extract_pdf_text_fragments(array_body: bytes) -> list[str]:
    fragments: list[str] = []
    for literal_match in PDF_LITERAL_STRING_PATTERN.finditer(array_body):
        fragments.append(decode_pdf_literal_string(literal_match.group(0)))
    for hex_match in PDF_HEX_STRING_PATTERN.finditer(array_body):
        fragments.append(decode_pdf_hex_string(hex_match.group(1)))
    return [fragment for fragment in fragments if fragment]


def decode_pdf_literal_string(token: bytes) -> str:
    content = token[1:-1]
    decoded_bytes = bytearray()
    index = 0
    while index < len(content):
        current = content[index]
        if current != 0x5C:  # backslash
            decoded_bytes.append(current)
            index += 1
            continue

        index += 1
        if index >= len(content):
            break

        escaped = content[index]
        escape_map = {
            ord("n"): b"\n",
            ord("r"): b"\r",
            ord("t"): b"\t",
            ord("b"): b"\b",
            ord("f"): b"\f",
            ord("("): b"(",
            ord(")"): b")",
            ord("\\"): b"\\",
        }
        mapped = escape_map.get(escaped)
        if mapped is not None:
            decoded_bytes.extend(mapped)
            index += 1
            continue

        if 48 <= escaped <= 55:
            octal_digits = bytes([escaped])
            for _ in range(2):
                if index + 1 < len(content) and 48 <= content[index + 1] <= 55:
                    index += 1
                    octal_digits += bytes([content[index]])
                else:
                    break
            decoded_bytes.append(int(octal_digits, 8))
            index += 1
            continue

        decoded_bytes.append(escaped)
        index += 1

    return decode_pdf_string_bytes(bytes(decoded_bytes))


def decode_pdf_hex_string(hex_bytes: bytes) -> str:
    cleaned = re.sub(rb"\s+", b"", hex_bytes)
    if len(cleaned) % 2 == 1:
        cleaned += b"0"
    try:
        decoded_bytes = bytes.fromhex(cleaned.decode("ascii"))
    except ValueError:
        return ""
    return decode_pdf_string_bytes(decoded_bytes)


def decode_pdf_string_bytes(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    if raw_bytes.startswith(b"\xfe\xff") or raw_bytes.startswith(b"\xff\xfe"):
        for encoding in ("utf-16", "utf-16-be", "utf-16-le"):
            try:
                return raw_bytes.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


def parse_docx_styles(styles_xml: bytes | None) -> dict[str, str]:
    if not styles_xml:
        return {}
    try:
        root = ElementTree.fromstring(styles_xml)
    except ElementTree.ParseError:
        return {}

    styles: dict[str, str] = {}
    for style in root.findall(".//w:style", WORDPROCESSINGML_NS):
        style_id = style.get(f"{{{WORDPROCESSINGML_NS['w']}}}styleId")
        style_name_element = style.find("w:name", WORDPROCESSINGML_NS)
        style_name = (
            style_name_element.get(f"{{{WORDPROCESSINGML_NS['w']}}}val")
            if style_name_element is not None
            else None
        )
        if style_id:
            styles[style_id] = style_name or style_id
    return styles


def extract_docx_paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iterfind(".//w:t", WORDPROCESSINGML_NS):
        if node.text:
            parts.append(node.text)
    return "".join(parts).strip()


def extract_docx_paragraph_style_id(paragraph: ElementTree.Element) -> str | None:
    style_element = paragraph.find(".//w:pPr/w:pStyle", WORDPROCESSINGML_NS)
    if style_element is None:
        return None
    return style_element.get(f"{{{WORDPROCESSINGML_NS['w']}}}val")


def is_docx_heading_style(*, style_id: str | None, style_name: str | None) -> bool:
    candidates = [
        item.strip().lower()
        for item in (style_id, style_name)
        if isinstance(item, str) and item.strip()
    ]
    return any(candidate.startswith("heading") or candidate == "title" for candidate in candidates)


def _resolve_chunk_end(
    *,
    text: str,
    start: int,
    max_end: int,
    chunk_size: int,
) -> int:
    if max_end >= len(text):
        return len(text)

    lower_bound = min(len(text), start + max(1, chunk_size // 2))
    newline_boundary = text.rfind("\n", lower_bound, max_end)
    if newline_boundary > start:
        return newline_boundary

    space_boundary = text.rfind(" ", lower_bound, max_end)
    if space_boundary > start:
        return space_boundary

    return max_end
