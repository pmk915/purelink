from __future__ import annotations

from pathlib import Path
import shutil

from app.core.config import Settings, get_settings
from app.schemas.llm import (
    DEEPSEEK_PROVIDER,
    HEURISTIC_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
)
from app.schemas.provider_status import ProviderStatusRead, SystemProviderStatusRead
from app.services.asr_provider import VOSK_ASR_PROVIDER
from app.services.embedding_provider import (
    DEFAULT_FASTEMBED_MODEL,
    FASTEMBED_PROVIDER,
    LOCAL_HASHED_BOW_PROVIDER,
    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER,
    SENTENCE_TRANSFORMERS_PROVIDER,
)
from app.services.ocr_provider import TESSERACT_OCR_PROVIDER
from app.services.reranking import LOCAL_RULE_RERANKER


LOCAL_DEMO_MODE = "local_demo"
LOCAL_MODEL_MODE = "local_model"
EXTERNAL_API_MODE = "external_api"
LOCAL_TOOL_MODE = "local_tool"
DISABLED_MODE = "disabled"
UNSUPPORTED_MODE = "unsupported"


def build_provider_status(
    settings: Settings | None = None,
) -> SystemProviderStatusRead:
    active_settings = settings or get_settings()
    return SystemProviderStatusRead(
        llm=build_llm_status(active_settings),
        embedding=build_embedding_status(active_settings),
        ocr=build_ocr_status(active_settings),
        asr=build_asr_status(active_settings),
        reranker=build_reranker_status(active_settings),
    )


def build_llm_status(settings: Settings) -> ProviderStatusRead:
    provider = settings.llm_provider
    if provider == HEURISTIC_PROVIDER:
        return ProviderStatusRead(
            provider=provider,
            configured=True,
            requires_api_key=False,
            mode=LOCAL_DEMO_MODE,
            message="本地演示模式，不需要 LLM_API_KEY，回答质量适合 demo。",
        )

    if provider == OPENAI_COMPATIBLE_PROVIDER:
        base_url_configured = bool(settings.llm_api_base)
        api_key_configured = bool(settings.llm_api_key)
        model_configured = bool(settings.llm_model)
        configured = base_url_configured and api_key_configured and model_configured
        missing = _missing_items(
            ("LLM_API_BASE_URL", base_url_configured),
            ("LLM_API_KEY", api_key_configured),
            ("LLM_MODEL", model_configured),
        )
        message = (
            "外部 LLM Provider 已配置。"
            if configured
            else f"外部 LLM Provider 缺少配置：{', '.join(missing)}。"
        )
        return ProviderStatusRead(
            provider=provider,
            configured=configured,
            requires_api_key=True,
            mode=EXTERNAL_API_MODE,
            message=message,
            model=settings.llm_model or None,
            base_url_configured=base_url_configured,
            api_key_configured=api_key_configured,
        )

    if provider == DEEPSEEK_PROVIDER:
        base_url_configured = bool(settings.llm_api_base)
        api_key_configured = bool(settings.llm_api_key)
        model_configured = bool(settings.llm_model)
        configured = base_url_configured and api_key_configured and model_configured
        missing = _missing_items(
            ("LLM_API_BASE_URL", base_url_configured),
            ("LLM_API_KEY", api_key_configured),
            ("LLM_MODEL", model_configured),
        )
        message = (
            "DeepSeek Provider 已配置。"
            if configured
            else f"DeepSeek Provider 缺少配置：{', '.join(missing)}。"
        )
        return ProviderStatusRead(
            provider=provider,
            configured=configured,
            requires_api_key=True,
            mode=EXTERNAL_API_MODE,
            message=message,
            model=settings.llm_model or None,
            base_url_configured=base_url_configured,
            api_key_configured=api_key_configured,
        )

    return _unsupported_status(
        provider=provider,
        message=(
            "不支持的 LLM_PROVIDER。可用值："
            f"{HEURISTIC_PROVIDER}, {OPENAI_COMPATIBLE_PROVIDER}, {DEEPSEEK_PROVIDER}。"
        ),
    )


def build_embedding_status(settings: Settings) -> ProviderStatusRead:
    provider = settings.embedding_provider
    if provider == LOCAL_HASHED_BOW_PROVIDER:
        return ProviderStatusRead(
            provider=provider,
            configured=True,
            requires_api_key=False,
            mode=LOCAL_DEMO_MODE,
            message="本地 fallback embedding，适合极简 demo。默认推荐改用 fastembed 获得真实语义检索。",
            model=settings.embedding_model or None,
        )

    if provider == FASTEMBED_PROVIDER:
        model = settings.embedding_model or DEFAULT_FASTEMBED_MODEL
        return ProviderStatusRead(
            provider=provider,
            configured=True,
            requires_api_key=False,
            mode=LOCAL_MODEL_MODE,
            message="本地 fastembed embedding 已启用。首次运行会下载模型，切换模型后需要重新索引已有文档。",
            model=model,
        )

    if provider == SENTENCE_TRANSFORMERS_PROVIDER:
        model_configured = bool(settings.embedding_model)
        message = (
            "本地 sentence_transformers embedding 已配置。首次运行会下载模型，切换模型后需要重新索引已有文档。"
            if model_configured
            else "sentence_transformers 需要配置 EMBEDDING_MODEL。"
        )
        return ProviderStatusRead(
            provider=provider,
            configured=model_configured,
            requires_api_key=False,
            mode=LOCAL_MODEL_MODE,
            message=message,
            model=settings.embedding_model or None,
        )

    if provider == OPENAI_COMPATIBLE_EMBEDDING_PROVIDER:
        base_url_configured = bool(settings.embedding_api_base)
        api_key_configured = bool(settings.embedding_api_key)
        model_configured = bool(settings.embedding_model)
        configured = base_url_configured and api_key_configured and model_configured
        missing = _missing_items(
            ("EMBEDDING_API_BASE_URL", base_url_configured),
            ("EMBEDDING_API_KEY", api_key_configured),
            ("EMBEDDING_MODEL", model_configured),
        )
        message = (
            "外部 Embedding Provider 已配置。切换 provider 或 model 后，需要重新索引已有文档。"
            if configured
            else f"外部 Embedding Provider 缺少配置：{', '.join(missing)}。"
        )
        return ProviderStatusRead(
            provider=provider,
            configured=configured,
            requires_api_key=True,
            mode=EXTERNAL_API_MODE,
            message=message,
            model=settings.embedding_model or None,
            base_url_configured=base_url_configured,
            api_key_configured=api_key_configured,
        )

    return _unsupported_status(
        provider=provider,
        message=(
            "不支持的 EMBEDDING_PROVIDER。可用值："
            f"{LOCAL_HASHED_BOW_PROVIDER}, {FASTEMBED_PROVIDER}, {SENTENCE_TRANSFORMERS_PROVIDER}, "
            f"{OPENAI_COMPATIBLE_EMBEDDING_PROVIDER}。"
        ),
    )


def build_ocr_status(settings: Settings) -> ProviderStatusRead:
    provider = settings.ocr_provider
    if not settings.enable_ocr or provider in {"", "disabled"}:
        return ProviderStatusRead(
            provider=provider or "disabled",
            configured=True,
            requires_api_key=False,
            mode=DISABLED_MODE,
            message="OCR 扩展默认关闭。Core 版本不处理图片 OCR 和扫描 PDF OCR。",
        )
    if provider != TESSERACT_OCR_PROVIDER:
        return _unsupported_status(
            provider=provider,
            message=f"不支持的 OCR_PROVIDER。当前支持：{TESSERACT_OCR_PROVIDER}。",
        )

    binary_available = _command_available(settings.ocr_tesseract_command)
    message = (
        "OCR Provider 已配置。"
        if binary_available
        else "OCR Provider 已配置，但当前环境找不到 tesseract 命令；图片和扫描 PDF OCR 可能失败。"
    )
    return ProviderStatusRead(
        provider=provider,
        configured=True,
        requires_api_key=False,
        mode=LOCAL_TOOL_MODE,
        message=message,
        model=settings.ocr_language,
        binary_available=binary_available,
    )


def build_asr_status(settings: Settings) -> ProviderStatusRead:
    provider = settings.asr_provider
    if not settings.enable_media or provider in {"", "disabled"}:
        return ProviderStatusRead(
            provider=provider or "disabled",
            configured=True,
            requires_api_key=False,
            mode=DISABLED_MODE,
            message="媒体转写扩展默认关闭。Core 版本不处理音频和视频文件。",
        )
    if provider != VOSK_ASR_PROVIDER:
        return _unsupported_status(
            provider=provider,
            message=f"不支持的 ASR_PROVIDER。当前支持：{VOSK_ASR_PROVIDER}。",
        )

    model_path = Path(settings.asr_vosk_model_path).expanduser()
    model_path_exists = model_path.exists()
    ffmpeg_available = _command_available(settings.asr_ffmpeg_command)
    configured = model_path_exists and ffmpeg_available
    if configured:
        message = "ASR Provider 已配置。"
    elif not model_path_exists and not ffmpeg_available:
        message = "ASR Provider 已配置，但 Vosk 模型路径不存在，且 ffmpeg 不可用。"
    elif not model_path_exists:
        message = "ASR Provider 已配置，但 Vosk 模型路径不存在；音频和视频处理会失败。"
    else:
        message = "ASR Provider 已配置，但 ffmpeg 不可用；音频转换和视频抽音会失败。"

    return ProviderStatusRead(
        provider=provider,
        configured=configured,
        requires_api_key=False,
        mode=LOCAL_TOOL_MODE,
        message=message,
        model=settings.asr_vosk_model_path,
        model_path_exists=model_path_exists,
        binary_available=ffmpeg_available,
    )


def build_reranker_status(settings: Settings) -> ProviderStatusRead:
    provider = settings.reranker_provider
    if provider == LOCAL_RULE_RERANKER:
        return ProviderStatusRead(
            provider=provider,
            configured=True,
            requires_api_key=False,
            mode=LOCAL_DEMO_MODE,
            message="本地轻量规则 rerank 已启用。",
        )

    return _unsupported_status(
        provider=provider,
        message=f"不支持的 RERANKER_PROVIDER。当前支持：{LOCAL_RULE_RERANKER}。",
    )


def _unsupported_status(*, provider: str, message: str) -> ProviderStatusRead:
    return ProviderStatusRead(
        provider=provider,
        configured=False,
        requires_api_key=False,
        mode=UNSUPPORTED_MODE,
        message=message,
    )


def _missing_items(*items: tuple[str, bool]) -> list[str]:
    return [name for name, configured in items if not configured]


def _command_available(command: str) -> bool:
    normalized = command.strip()
    if not normalized:
        return False
    if Path(normalized).is_absolute():
        return Path(normalized).exists()
    return shutil.which(normalized) is not None
