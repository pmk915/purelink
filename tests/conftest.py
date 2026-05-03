from __future__ import annotations

import pytest

from app.core.config import get_settings

OPTIONAL_CORE_EXTENSION_PATTERNS = (
    "test_personal_pdf_garbled_direct_text_falls_back_to_ocr",
    "test_personal_pdf_garbled_direct_text_reports_ocr_unavailable",
    "test_personal_pdf_garbled_direct_text_reports_ocr_no_text_found",
    "test_personal_scanned_pdf_process_uses_ocr_and_preserves_page_metadata",
    "test_personal_scanned_pdf_process_failure_marks_document_failed_for_ocr_error",
    "test_personal_scanned_pdf_",
    "test_personal_image_",
    "test_personal_audio_",
    "test_personal_video_",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_optional_extension = pytest.mark.skip(
        reason="Optional OCR/media extension coverage is disabled in PureLink Core."
    )
    optional_extension_files = {
        "tests/test_ocr_provider.py",
    }

    for item in items:
        nodeid = item.nodeid
        if any(nodeid.startswith(prefix) for prefix in optional_extension_files):
            item.add_marker(skip_optional_extension)
            continue
        if any(pattern in nodeid for pattern in OPTIONAL_CORE_EXTENSION_PATTERNS):
            item.add_marker(skip_optional_extension)


@pytest.fixture(autouse=True)
def _core_test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.delenv("LLM_API_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("LLM_THINKING_ENABLED", raising=False)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hashed_bow")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("ENABLE_OCR", "false")
    monkeypatch.setenv("OCR_PROVIDER", "disabled")
    monkeypatch.setenv("ENABLE_MEDIA", "false")
    monkeypatch.setenv("ASR_PROVIDER", "disabled")
    monkeypatch.setenv("MULTIMODAL_PROVIDER", "disabled")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
