from __future__ import annotations

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CHUNK_LENGTH = 250
MAX_TEXT_CHARACTERS = 25_000
STREAM_CROSSFADE_MS = 32
DEFAULT_INTER_CHUNK_PAUSE_MS = 45

# Kokoro generation is less knob-heavy than the previous runtime; keep v1 defaults minimal.
DEFAULT_SYNTHESIS_KWARGS = {
    "speed": 1.0,
}

MAX_RMS_GAIN = 1.20
MIN_RMS_GAIN = 0.83

MODEL_ID_ENV_VAR = "MODEL_ID"
HF_HOME_ENV_VAR = "HF_HOME"
HUGGINGFACE_HUB_CACHE_ENV_VAR = "HUGGINGFACE_HUB_CACHE"
TTS_DEVICE_ENV_VAR = "TTS_DEVICE"

DEFAULT_MODEL_ID = "hexgrad/Kokoro-82M"

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en",)
ALLOWED_TTS_DEVICES = {"auto", "cuda", "cpu"}


def _optional_env(var_name: str) -> str | None:
    value = os.getenv(var_name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def resolve_model_id() -> str:
    return _optional_env(MODEL_ID_ENV_VAR) or DEFAULT_MODEL_ID


def resolve_optional_path(var_name: str) -> Path | None:
    value = _optional_env(var_name)
    if value is None:
        return None
    return _resolve_path(value)


def resolve_tts_device_setting() -> str:
    raw = (os.getenv(TTS_DEVICE_ENV_VAR, "auto") or "auto").strip().lower()
    if raw not in ALLOWED_TTS_DEVICES:
        expected = ", ".join(sorted(ALLOWED_TTS_DEVICES))
        raise ValueError(
            f"Invalid {TTS_DEVICE_ENV_VAR}: {raw!r}. Expected one of: {expected}"
        )
    return raw


def resolve_kokoro_device(device_setting: str) -> str | None:
    normalized = (device_setting or "auto").strip().lower()
    if normalized == "auto":
        return None
    return normalized


def normalize_language_code(language: str | None) -> str:
    raw = (language or DEFAULT_LANGUAGE).strip().lower()
    if not raw:
        return DEFAULT_LANGUAGE

    if raw.startswith("en"):
        return "en"

    supported = ", ".join(SUPPORTED_LANGUAGES)
    raise ValueError(
        f"Unsupported language: {language!r}. Supported languages: [{supported}]"
    )


MODEL_ID = resolve_model_id()
HF_HOME = resolve_optional_path(HF_HOME_ENV_VAR)
HUGGINGFACE_HUB_CACHE = resolve_optional_path(HUGGINGFACE_HUB_CACHE_ENV_VAR)
TTS_DEVICE_SETTING = resolve_tts_device_setting()
TTS_DEVICE = resolve_kokoro_device(TTS_DEVICE_SETTING)

MODE = (os.getenv("TTS_MODE", "local") or "local").strip().lower()
ALLOWED_MODES = {"local", "runpod"}

TTS_HOST = os.getenv("TTS_HOST", "0.0.0.0")
TTS_PORT = int(os.getenv("TTS_PORT", "5000"))
LOCAL_JOB_TTL_SECONDS = max(60, int(os.getenv("LOCAL_JOB_TTL_SECONDS", "3600")))
LOCAL_JOB_MAX_TERMINAL = max(10, int(os.getenv("LOCAL_JOB_MAX_TERMINAL", "200")))


def validate_mode(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    if normalized not in ALLOWED_MODES:
        expected = ", ".join(sorted(ALLOWED_MODES))
        raise ValueError(f"Invalid TTS_MODE: {mode!r}. Expected one of: {expected}")
    return normalized


def configure_stdio() -> None:
    """Avoid Windows stdout/stderr crashes on non-ASCII log messages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except ValueError:
                continue
