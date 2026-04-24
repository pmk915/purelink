from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
import io
from pathlib import Path
import subprocess
from typing import Protocol

from app.core.config import Settings, get_settings


TESSERACT_OCR_PROVIDER = "tesseract"


class OCRProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OCRRegion:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class OCRResult:
    text: str
    provider_name: str
    provider_version: str
    language: str | None = None
    confidence: float | None = None
    regions: tuple[OCRRegion, ...] = ()


class OCRProvider(Protocol):
    provider_name: str
    provider_version: str

    def extract_text(self, image_path: Path) -> OCRResult: ...


@dataclass(frozen=True, slots=True)
class _TesseractWord:
    page_num: int
    block_num: int
    paragraph_num: int
    line_num: int
    left: int
    top: int
    width: int
    height: int
    confidence: float | None
    text: str


class TesseractOCRProvider:
    provider_name = TESSERACT_OCR_PROVIDER

    def __init__(
        self,
        *,
        command: str = "tesseract",
        language: str = "eng",
        page_segmentation_mode: int = 6,
    ) -> None:
        self.command = command
        self.language = language
        self.page_segmentation_mode = page_segmentation_mode
        self.provider_version = _detect_tesseract_version(command)

    def extract_text(self, image_path: Path) -> OCRResult:
        if not image_path.exists():
            raise OCRProviderError("Image source file does not exist.")

        try:
            completed = subprocess.run(
                [
                    self.command,
                    str(image_path),
                    "stdout",
                    "--psm",
                    str(self.page_segmentation_mode),
                    "-l",
                    self.language,
                    "tsv",
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise OCRProviderError("OCR provider is not available.") from exc

        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "OCR extraction failed."
            raise OCRProviderError(message)

        words = _parse_tesseract_tsv(completed.stdout)
        if not words:
            raise OCRProviderError("OCR did not extract readable text from the image.")

        regions = _group_words_into_regions(words)
        text = "\n".join(region.text for region in regions).strip()
        if not text:
            raise OCRProviderError("OCR did not extract readable text from the image.")

        confidences = [
            region.confidence
            for region in regions
            if region.confidence is not None
        ]
        average_confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else None
        )
        return OCRResult(
            text=text,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            language=self.language,
            confidence=average_confidence,
            regions=tuple(regions),
        )


def resolve_ocr_provider(
    provider: str | None = None,
    *,
    settings: Settings | None = None,
) -> OCRProvider:
    active_settings = settings or get_settings()
    normalized_provider = (provider or active_settings.ocr_provider).strip().lower()

    if normalized_provider == TESSERACT_OCR_PROVIDER:
        return TesseractOCRProvider(
            command=active_settings.ocr_tesseract_command,
            language=active_settings.ocr_language,
            page_segmentation_mode=active_settings.ocr_tesseract_psm,
        )

    raise OCRProviderError(f"Unsupported OCR provider: {normalized_provider}.")


@lru_cache(maxsize=4)
def _detect_tesseract_version(command: str) -> str:
    try:
        completed = subprocess.run(
            [command, "--version"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return "unknown"

    if completed.returncode != 0:
        return "unknown"

    first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
    return first_line or "unknown"


def _parse_tesseract_tsv(raw_tsv: str) -> list[_TesseractWord]:
    reader = csv.DictReader(io.StringIO(raw_tsv), delimiter="\t")
    words: list[_TesseractWord] = []

    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue

        try:
            level = int(row.get("level") or "0")
        except ValueError:
            continue
        if level != 5:
            continue

        try:
            words.append(
                _TesseractWord(
                    page_num=int(row.get("page_num") or "0"),
                    block_num=int(row.get("block_num") or "0"),
                    paragraph_num=int(row.get("par_num") or "0"),
                    line_num=int(row.get("line_num") or "0"),
                    left=int(row.get("left") or "0"),
                    top=int(row.get("top") or "0"),
                    width=int(row.get("width") or "0"),
                    height=int(row.get("height") or "0"),
                    confidence=_parse_confidence(row.get("conf")),
                    text=text,
                )
            )
        except ValueError:
            continue

    words.sort(
        key=lambda item: (
            item.page_num,
            item.block_num,
            item.paragraph_num,
            item.line_num,
            item.left,
            item.top,
        )
    )
    return words


def _group_words_into_regions(words: list[_TesseractWord]) -> list[OCRRegion]:
    grouped_words: dict[tuple[int, int, int, int], list[_TesseractWord]] = {}
    for word in words:
        grouped_words.setdefault(
            (
                word.page_num,
                word.block_num,
                word.paragraph_num,
                word.line_num,
            ),
            [],
        ).append(word)

    regions: list[OCRRegion] = []
    for key in sorted(grouped_words):
        line_words = grouped_words[key]
        left = min(item.left for item in line_words)
        top = min(item.top for item in line_words)
        right = max(item.left + item.width for item in line_words)
        bottom = max(item.top + item.height for item in line_words)
        confidences = [
            item.confidence
            for item in line_words
            if item.confidence is not None
        ]
        average_confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else None
        )
        regions.append(
            OCRRegion(
                text=" ".join(item.text for item in line_words).strip(),
                left=left,
                top=top,
                width=max(right - left, 0),
                height=max(bottom - top, 0),
                confidence=average_confidence,
            )
        )
    return regions


def _parse_confidence(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None

    try:
        confidence = float(raw_value)
    except ValueError:
        return None

    if confidence < 0:
        return None
    return confidence
