from __future__ import annotations

from app.services.text_quality import TextQualityStatus, detect_text_quality, sanitize_text


def test_sanitize_text_removes_nul_and_control_characters() -> None:
    sanitized = sanitize_text("alpha\x00\r\nbeta\x0f\tgamma")

    assert "\x00" not in sanitized
    assert "\x0f" not in sanitized
    assert sanitized == "alpha\nbeta gamma"


def test_detect_text_quality_marks_garbled_text() -> None:
    report = detect_text_quality("□□□□□□◇◇◇◇◇◇")

    assert report.status == TextQualityStatus.GARBLED


def test_detect_text_quality_marks_binary_like_text() -> None:
    report = detect_text_quality("alpha\x00beta")

    assert report.status == TextQualityStatus.BINARY_LIKE
