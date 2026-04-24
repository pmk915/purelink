from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Protocol
import wave

from app.core.config import Settings, get_settings


VOSK_ASR_PROVIDER = "vosk"
DEFAULT_ASR_SAMPLE_RATE = 16000


class ASRProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ASRSegment:
    text: str
    start_time: float | None = None
    end_time: float | None = None


@dataclass(frozen=True, slots=True)
class ASRResult:
    full_text: str
    provider_name: str
    provider_version: str
    segments: tuple[ASRSegment, ...]


class ASRProvider(Protocol):
    provider_name: str
    provider_version: str

    def transcribe(self, audio_path: Path) -> ASRResult: ...


class VoskASRProvider:
    provider_name = VOSK_ASR_PROVIDER

    def __init__(
        self,
        *,
        ffmpeg_command: str = "ffmpeg",
        model_path: str,
    ) -> None:
        self.ffmpeg_command = ffmpeg_command
        self.model_path = Path(model_path).expanduser()
        self.provider_version = self.model_path.name or "unknown"

    def transcribe(self, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise ASRProviderError("Audio source file does not exist.")
        if self.model_path.as_posix().strip() == "":
            raise ASRProviderError("ASR model path is not configured.")
        if not self.model_path.exists():
            raise ASRProviderError("ASR model path is not available.")

        with TemporaryDirectory(prefix="purelink-audio-asr-") as tmp_dir:
            normalized_wav_path = Path(tmp_dir) / "normalized.wav"
            _convert_audio_to_wav(
                audio_path=audio_path,
                output_path=normalized_wav_path,
                ffmpeg_command=self.ffmpeg_command,
            )
            segments = _transcribe_wav_with_vosk(
                wav_path=normalized_wav_path,
                model_path=self.model_path,
            )

        if not segments:
            raise ASRProviderError("ASR did not extract readable text from the audio.")

        full_text = " ".join(segment.text for segment in segments).strip()
        if not full_text:
            raise ASRProviderError("ASR did not extract readable text from the audio.")

        return ASRResult(
            full_text=full_text,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            segments=tuple(segments),
        )


def resolve_asr_provider(
    provider: str | None = None,
    *,
    settings: Settings | None = None,
) -> ASRProvider:
    active_settings = settings or get_settings()
    normalized_provider = (provider or active_settings.asr_provider).strip().lower()

    if normalized_provider == VOSK_ASR_PROVIDER:
        return VoskASRProvider(
            ffmpeg_command=active_settings.asr_ffmpeg_command,
            model_path=active_settings.asr_vosk_model_path,
        )

    raise ASRProviderError(f"Unsupported ASR provider: {normalized_provider}.")


def _convert_audio_to_wav(
    *,
    audio_path: Path,
    output_path: Path,
    ffmpeg_command: str,
) -> None:
    try:
        completed = subprocess.run(
            [
                ffmpeg_command,
                "-y",
                "-i",
                str(audio_path),
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
        raise ASRProviderError("ASR audio conversion tool is not available.") from exc

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Audio conversion failed."
        )
        raise ASRProviderError(message)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ASRProviderError("Audio conversion failed.")


def _transcribe_wav_with_vosk(
    *,
    wav_path: Path,
    model_path: Path,
) -> list[ASRSegment]:
    try:
        from vosk import KaldiRecognizer
    except ModuleNotFoundError as exc:
        raise ASRProviderError("ASR provider dependencies are not installed.") from exc

    model = _load_vosk_model(model_path)

    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            recognizer = KaldiRecognizer(model, wav_file.getframerate())
            recognizer.SetWords(True)
            segments: list[ASRSegment] = []

            while True:
                chunk = wav_file.readframes(4000)
                if not chunk:
                    break
                if recognizer.AcceptWaveform(chunk):
                    segment = _build_vosk_segment(recognizer.Result())
                    if segment is not None:
                        segments.append(segment)

            final_segment = _build_vosk_segment(recognizer.FinalResult())
            if final_segment is not None:
                segments.append(final_segment)
            return segments
    except wave.Error as exc:
        raise ASRProviderError("Audio stream is not a valid WAV input for ASR.") from exc


@lru_cache(maxsize=2)
def _load_vosk_model(model_path: Path):
    try:
        from vosk import Model, SetLogLevel
    except ModuleNotFoundError as exc:
        raise ASRProviderError("ASR provider dependencies are not installed.") from exc

    try:
        SetLogLevel(-1)
    except Exception:
        pass

    try:
        return Model(str(model_path))
    except Exception as exc:  # pragma: no cover - library error surface
        raise ASRProviderError("ASR model could not be loaded.") from exc


def _build_vosk_segment(raw_payload: str) -> ASRSegment | None:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        payload = {}

    if not isinstance(payload, dict):
        return None

    text = " ".join(str(payload.get("text", "")).split()).strip()
    if not text:
        return None

    words = payload.get("result")
    start_time: float | None = None
    end_time: float | None = None
    if isinstance(words, list) and words:
        first_word = words[0] if isinstance(words[0], dict) else None
        last_word = words[-1] if isinstance(words[-1], dict) else None
        if isinstance(first_word, dict) and isinstance(first_word.get("start"), (int, float)):
            start_time = float(first_word["start"])
        if isinstance(last_word, dict) and isinstance(last_word.get("end"), (int, float)):
            end_time = float(last_word["end"])

    return ASRSegment(
        text=text,
        start_time=start_time,
        end_time=end_time,
    )
