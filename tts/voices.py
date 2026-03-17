from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import soundfile as sf

from .config import (
    VOICE_REFERENCES_DIR,
    VOICE_REFERENCES_MANIFEST_PATH,
    VOICE_REFERENCE_MAX_DURATION,
    VOICE_REFERENCE_MIN_DURATION,
    VOICE_REFERENCE_SAMPLE_RATE,
)


VOICE_PRESETS = {
    "Claribel Dervla": {"name": "Claribel Dervla", "gender": "female"},
    "Daisy Studious": {"name": "Daisy Studious", "gender": "female"},
    "Gracie Wise": {"name": "Gracie Wise", "gender": "female"},
    "Ana Florence": {"name": "Ana Florence", "gender": "female"},
    "Andrew Chipper": {"name": "Andrew Chipper", "gender": "male"},
    "Viktor Eka": {"name": "Viktor Eka", "gender": "male"},
    "Gilberto Mathias": {"name": "Gilberto Mathias", "gender": "male"},
    "Damien Black": {"name": "Damien Black", "gender": "male"},
}


def validate_reference_file(file_path: Path) -> float:
    """Validate reference WAV format and return duration in seconds."""
    if not file_path.exists():
        raise FileNotFoundError(f"Voice reference file not found: {file_path}")

    info = sf.info(str(file_path))
    duration = info.frames / info.samplerate if info.samplerate else 0.0

    if info.format != "WAV":
        raise ValueError(f"{file_path.name}: expected WAV, got {info.format}")
    if info.subtype != "PCM_16":
        raise ValueError(f"{file_path.name}: expected PCM_16, got {info.subtype}")
    if info.channels != 1:
        raise ValueError(f"{file_path.name}: expected mono, got {info.channels} channels")
    if info.samplerate != VOICE_REFERENCE_SAMPLE_RATE:
        raise ValueError(
            f"{file_path.name}: expected {VOICE_REFERENCE_SAMPLE_RATE} Hz, got {info.samplerate} Hz"
        )
    if not (VOICE_REFERENCE_MIN_DURATION <= duration <= VOICE_REFERENCE_MAX_DURATION):
        raise ValueError(
            f"{file_path.name}: expected duration between {VOICE_REFERENCE_MIN_DURATION} and "
            f"{VOICE_REFERENCE_MAX_DURATION} sec, got {duration:.3f} sec"
        )

    return round(duration, 3)


def load_reference_voices() -> Dict[str, dict]:
    """Load local voice references from manifest.json."""
    if not VOICE_REFERENCES_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Voice reference manifest not found: {VOICE_REFERENCES_MANIFEST_PATH}"
        )

    manifest = json.loads(VOICE_REFERENCES_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Voice reference manifest must contain a non-empty list")

    required_fields = {"id", "name", "gender", "file", "source_url", "license"}
    references: Dict[str, dict] = {}

    for entry in manifest:
        missing_fields = required_fields - entry.keys()
        if missing_fields:
            raise ValueError(f"Voice reference entry missing fields: {sorted(missing_fields)}")

        voice_id = entry["id"]
        if voice_id in references or voice_id in VOICE_PRESETS:
            raise ValueError(f"Duplicate voice id detected: {voice_id}")

        file_path = VOICE_REFERENCES_DIR / entry["file"]
        duration_sec = validate_reference_file(file_path)

        references[voice_id] = {
            **entry,
            "path": str(file_path),
            "duration_sec": duration_sec,
        }

    return references


REFERENCE_VOICES = load_reference_voices()


def list_available_voices() -> list:
    voices = [
        {
            "id": voice_id,
            "name": info["name"],
            "gender": info["gender"],
            "source_type": "reference",
        }
        for voice_id, info in REFERENCE_VOICES.items()
    ]
    voices.extend(
        {
            "id": voice_id,
            "name": info["name"],
            "gender": info["gender"],
            "source_type": "preset",
        }
        for voice_id, info in VOICE_PRESETS.items()
    )
    return voices


def resolve_voice(voice_id: str | None = None) -> dict:
    """Return XTTS-compatible speaker selection config."""
    if voice_id:
        if voice_id in REFERENCE_VOICES:
            info = REFERENCE_VOICES[voice_id]
            return {
                "id": voice_id,
                "name": info["name"],
                "source_type": "reference",
                "speaker_wav": info["path"],
                "speaker_id": None,
            }
        if voice_id in VOICE_PRESETS:
            info = VOICE_PRESETS[voice_id]
            return {
                "id": voice_id,
                "name": info["name"],
                "source_type": "preset",
                "speaker_wav": None,
                "speaker_id": voice_id,
            }
        raise ValueError(f"Unknown voice_id: {voice_id}")

    default_reference_id = next(iter(REFERENCE_VOICES), None)
    if default_reference_id:
        return resolve_voice(default_reference_id)

    default_preset_id = next(iter(VOICE_PRESETS), None)
    if default_preset_id:
        return resolve_voice(default_preset_id)

    raise RuntimeError("No voices configured")

