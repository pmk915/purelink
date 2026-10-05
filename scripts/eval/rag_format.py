"""Generate tiny local format fixtures for the existing deterministic eval runner."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

import fitz

from scripts.eval.rag_eval import RagEvalCase


FORMAT_SUFFIXES = {"txt": ".txt", "markdown": ".md", "docx": ".docx", "pdf": ".pdf"}


def generate_format_corpus(spec_path: Path, root: Path, cases: list[RagEvalCase]) -> list[dict]:
    documents = json.loads(spec_path.read_text(encoding="utf-8"))
    names = [document["name"] for document in documents]
    if len(names) != len(set(names)):
        raise ValueError("Format corpus names must be unique.")
    for case in cases:
        if case.document_format not in FORMAT_SUFFIXES:
            raise ValueError(f"Case {case.id} requires document_format.")
        for name in case.expected_doc_names:
            if name not in names:
                raise ValueError(f"Case {case.id} references missing corpus document {name}.")
            if Path(name).suffix != FORMAT_SUFFIXES[case.document_format]:
                raise ValueError(f"Case {case.id} format does not match {name}.")
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for document in documents:
        name, document_format = document["name"], document["format"]
        if Path(name).name != name or Path(name).suffix != FORMAT_SUFFIXES[document_format]:
            raise ValueError(f"Invalid corpus filename: {name}.")
        destination = root / name
        sections = [section for page in document["pages"] for section in page]
        if document_format in {"txt", "markdown"}:
            text = "\n\n".join(
                "\n".join([f"## {section['title']}", *section["paragraphs"]])
                for section in sections
            )
            destination.write_text(text + "\n", encoding="utf-8")
        elif document_format == "docx":
            _write_docx(destination, sections)
        else:
            _write_pdf(destination, document["pages"])
        manifest.append({
            "name": name,
            "path": name,
            "format": document_format,
            "size_bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        })
    return manifest


def _write_docx(path: Path, sections: list[dict]) -> None:
    paragraphs = []
    for section in sections:
        paragraphs.append(
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            f'<w:r><w:t>{escape(section["title"])}</w:t></w:r></w:p>'
        )
        paragraphs.extend(f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>" for text in section["paragraphs"])
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        ),
        "word/document.xml": (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{"".join(paragraphs)}</w:body></w:document>'
        ),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            # Fixed ZIP timestamps keep fixture hashes reproducible.
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), content.encode("utf-8"))


def _write_pdf(path: Path, pages: list[list[dict]]) -> None:
    with fitz.open() as pdf:
        for sections in pages:
            page = pdf.new_page()
            y = 72
            for section in sections:
                page.insert_text((72, y), section["title"], fontsize=12)
                y += 28
                for text in section["paragraphs"]:
                    bottom = min(y + 48, page.rect.height - 36)
                    if page.insert_textbox(fitz.Rect(72, y, 520, bottom), text, fontsize=10) < 0:
                        raise ValueError(f"PDF fixture text does not fit: {path.name}.")
                    y += 54
        pdf.save(path, no_new_id=True)
