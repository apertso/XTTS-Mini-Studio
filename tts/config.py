from __future__ import annotations

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
VOICE_REFERENCES_DIR = BASE_DIR / "assets" / "voice_references"
VOICE_REFERENCES_MANIFEST_PATH = VOICE_REFERENCES_DIR / "manifest.json"

VOICE_REFERENCE_SAMPLE_RATE = 22050
VOICE_REFERENCE_MIN_DURATION = 12.0
VOICE_REFERENCE_MAX_DURATION = 20.0

TOKENIZER_CHAR_LIMITS = {
    "en": 250,
    "de": 253,
    "fr": 273,
    "es": 239,
    "it": 213,
    "pt": 203,
    "pl": 224,
    "zh": 82,
    "ar": 166,
    "ru": 182,
    "nl": 251,
    "tr": 226,
    "ja": 71,
    "hu": 224,
    "ko": 95,
}

CHUNK_SAFETY_MARGIN = 16
MIN_CHUNK_LENGTH = 80
DEFAULT_CHUNK_LENGTH = 330
STORY_CHUNK_LIMIT_ADJUST = -12
STREAM_CROSSFADE_MS = 32

READING_MODE_DEFAULT = "default"
READING_MODE_STORY = "story"
READING_PROFILES = {
    READING_MODE_DEFAULT: {
        "synthesis_kwargs": {
            "temperature": 0.65,
            "top_p": 0.8,
            "top_k": 40,
            "repetition_penalty": 7.0,
            "length_penalty": 1.0,
        },
        "chunk_limit_adjust": 0,
        "inter_chunk_pause_ms": 45,
    },
    READING_MODE_STORY: {
        "synthesis_kwargs": {
            "speed": 0.92,
            "temperature": 0.60,
            "top_p": 0.78,
            "top_k": 35,
            "repetition_penalty": 6.5,
            "length_penalty": 1.0,
        },
        "chunk_limit_adjust": STORY_CHUNK_LIMIT_ADJUST,
        "inter_chunk_pause_ms": 180,
    },
}

MAX_RMS_GAIN = 1.20
MIN_RMS_GAIN = 0.83

MODEL_ID_ENV_VAR = "MODEL_ID"
MODEL_DIR_ENV_VAR = "MODEL_DIR"
LEGACY_MODEL_DIR_ENV_VAR = "XTTS_MODEL_DIR"
HF_HOME_ENV_VAR = "HF_HOME"
HUGGINGFACE_HUB_CACHE_ENV_VAR = "HUGGINGFACE_HUB_CACHE"

DEFAULT_MODEL_ID = "coqui/XTTS-v2"
DEFAULT_LOCAL_MODEL_DIR = BASE_DIR / "models" / "xtts_v2"


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


def resolve_model_dir() -> tuple[Path | None, str]:
    model_dir_env = _optional_env(MODEL_DIR_ENV_VAR)
    if model_dir_env:
        return _resolve_path(model_dir_env), MODEL_DIR_ENV_VAR

    legacy_model_dir_env = _optional_env(LEGACY_MODEL_DIR_ENV_VAR)
    if legacy_model_dir_env:
        return _resolve_path(legacy_model_dir_env), LEGACY_MODEL_DIR_ENV_VAR

    if DEFAULT_LOCAL_MODEL_DIR.exists():
        return DEFAULT_LOCAL_MODEL_DIR.resolve(), "default_local_model_dir"

    return None, "unset"


def resolve_optional_path(var_name: str) -> Path | None:
    value = _optional_env(var_name)
    if value is None:
        return None
    return _resolve_path(value)


MODEL_ID = resolve_model_id()
MODEL_DIR, MODEL_DIR_SOURCE = resolve_model_dir()
HF_HOME = resolve_optional_path(HF_HOME_ENV_VAR)
HUGGINGFACE_HUB_CACHE = resolve_optional_path(HUGGINGFACE_HUB_CACHE_ENV_VAR)

MODE = (os.getenv("TTS_MODE", "local") or "local").strip().lower()
ALLOWED_MODES = {"local", "runpod"}

PRECISION_ENV_VAR = "XTTS_PRECISION"
PRECISION_AUTO = "auto"
PRECISION_FP32 = "fp32"
PRECISION_FP16 = "fp16"
DEFAULT_PRECISION = PRECISION_AUTO
ALLOWED_PRECISIONS = {PRECISION_AUTO, PRECISION_FP32, PRECISION_FP16}

TTS_HOST = os.getenv("TTS_HOST", "0.0.0.0")
TTS_PORT = int(os.getenv("TTS_PORT", "5000"))


def validate_mode(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    if normalized not in ALLOWED_MODES:
        expected = ", ".join(sorted(ALLOWED_MODES))
        raise ValueError(f"Invalid TTS_MODE: {mode!r}. Expected one of: {expected}")
    return normalized


def validate_precision(precision: str) -> str:
    normalized = (precision or "").strip().lower()
    if normalized not in ALLOWED_PRECISIONS:
        expected = ", ".join(sorted(ALLOWED_PRECISIONS))
        raise ValueError(f"Invalid {PRECISION_ENV_VAR}: {precision!r}. Expected one of: {expected}")
    return normalized


def resolve_requested_precision() -> str:
    raw = (os.getenv(PRECISION_ENV_VAR, DEFAULT_PRECISION) or DEFAULT_PRECISION).strip().lower()
    return validate_precision(raw)


REQUESTED_PRECISION = resolve_requested_precision()


def resolve_effective_precision(
    mode: str, requested_precision: str, cuda_available: bool
) -> tuple[str, str | None]:
    normalized_mode = validate_mode(mode)
    normalized_precision = validate_precision(requested_precision)

    if not cuda_available:
        if normalized_precision == PRECISION_FP16:
            return (
                PRECISION_FP32,
                f"{PRECISION_ENV_VAR}=fp16 requested but CUDA is unavailable; falling back to fp32.",
            )
        return PRECISION_FP32, None

    if normalized_precision == PRECISION_FP32:
        return PRECISION_FP32, None
    if normalized_precision == PRECISION_FP16:
        return PRECISION_FP16, None

    if normalized_mode == "runpod":
        return PRECISION_FP16, None
    return PRECISION_FP32, None


def configure_stdio() -> None:
    """Avoid Windows stdout/stderr crashes on non-ASCII log messages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except ValueError:
                continue
