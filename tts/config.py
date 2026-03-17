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
DEFAULT_CHUNK_LENGTH = 340
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

MODEL_DIR_ENV_VAR = "XTTS_MODEL_DIR"
DEFAULT_MODEL_DIR = BASE_DIR / "models" / "xtts_v2"


def resolve_model_dir() -> Path:
    model_dir_env = (os.getenv(MODEL_DIR_ENV_VAR) or "").strip()
    model_dir = Path(model_dir_env).expanduser() if model_dir_env else DEFAULT_MODEL_DIR
    return model_dir.resolve()


MODEL_DIR = resolve_model_dir()

MODE = (os.getenv("TTS_MODE", "local") or "local").strip().lower()
ALLOWED_MODES = {"local", "runpod"}

TTS_HOST = os.getenv("TTS_HOST", "0.0.0.0")
TTS_PORT = int(os.getenv("TTS_PORT", "5000"))


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
