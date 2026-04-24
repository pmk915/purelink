from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from app.services.ocr_provider import (
    OCRProviderError,
    TesseractOCRProvider,
    _detect_tesseract_version,
    resolve_ocr_provider,
)


def test_tesseract_provider_extracts_text_and_regions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCompletedProcess:
        def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args, **kwargs):
        if args[1] == "--version":
            return FakeCompletedProcess(returncode=0, stdout="tesseract 5.4.0\n")
        return FakeCompletedProcess(
            returncode=0,
            stdout=(
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
                "5\t1\t1\t1\t1\t1\t10\t20\t40\t10\t96\tPureLink\n"
                "5\t1\t1\t1\t1\t2\t55\t20\t50\t10\t94\tOCR\n"
                "5\t1\t1\t1\t2\t1\t10\t40\t60\t10\t92\tsearchable\n"
            ),
        )

    monkeypatch.setattr("app.services.ocr_provider.subprocess.run", fake_run)
    _detect_tesseract_version.cache_clear()

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake image bytes")

    provider = TesseractOCRProvider(command="tesseract", language="eng", page_segmentation_mode=6)
    result = provider.extract_text(image_path)

    assert result.provider_name == "tesseract"
    assert result.provider_version == "tesseract 5.4.0"
    assert result.language == "eng"
    assert result.text == "PureLink OCR\nsearchable"
    assert len(result.regions) == 2
    assert result.regions[0].text == "PureLink OCR"
    assert result.regions[0].left == 10
    assert result.regions[0].width == 95


def test_tesseract_provider_reports_missing_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeCompletedProcess:
        def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args, **kwargs):
        if args[1] == "--version":
            return FakeCompletedProcess(returncode=1)
        raise OSError("tesseract missing")

    monkeypatch.setattr("app.services.ocr_provider.subprocess.run", fake_run)
    _detect_tesseract_version.cache_clear()

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake image bytes")

    provider = resolve_ocr_provider("tesseract")
    with pytest.raises(OCRProviderError, match="OCR provider is not available"):
        provider.extract_text(image_path)
