from __future__ import annotations

from typing import Dict


# English-only Kokoro voice catalog (American + British).
KOKORO_VOICES = [
    {"id": "af_heart", "name": "Heart (US)", "gender": "female", "locale": "en-US", "pipeline": "a"},
    {"id": "af_bella", "name": "Bella (US)", "gender": "female", "locale": "en-US", "pipeline": "a"},
    {"id": "af_nicole", "name": "Nicole (US)", "gender": "female", "locale": "en-US", "pipeline": "a"},
    {"id": "af_sarah", "name": "Sarah (US)", "gender": "female", "locale": "en-US", "pipeline": "a"},
    {"id": "af_sky", "name": "Sky (US)", "gender": "female", "locale": "en-US", "pipeline": "a"},
    {"id": "am_adam", "name": "Adam (US)", "gender": "male", "locale": "en-US", "pipeline": "a"},
    {"id": "am_michael", "name": "Michael (US)", "gender": "male", "locale": "en-US", "pipeline": "a"},
    {"id": "bf_emma", "name": "Emma (UK)", "gender": "female", "locale": "en-GB", "pipeline": "b"},
    {"id": "bf_isabella", "name": "Isabella (UK)", "gender": "female", "locale": "en-GB", "pipeline": "b"},
    {"id": "bf_alice", "name": "Alice (UK)", "gender": "female", "locale": "en-GB", "pipeline": "b"},
    {"id": "bf_lily", "name": "Lily (UK)", "gender": "female", "locale": "en-GB", "pipeline": "b"},
    {"id": "bm_george", "name": "George (UK)", "gender": "male", "locale": "en-GB", "pipeline": "b"},
    {"id": "bm_fable", "name": "Fable (UK)", "gender": "male", "locale": "en-GB", "pipeline": "b"},
    {"id": "bm_lewis", "name": "Lewis (UK)", "gender": "male", "locale": "en-GB", "pipeline": "b"},
    {"id": "bm_daniel", "name": "Daniel (UK)", "gender": "male", "locale": "en-GB", "pipeline": "b"},
]

VOICE_MAP: Dict[str, dict] = {voice["id"]: voice for voice in KOKORO_VOICES}
DEFAULT_VOICE_ID = KOKORO_VOICES[0]["id"]


def list_available_voices() -> list:
    return [
        {
            "id": voice["id"],
            "name": voice["name"],
            "gender": voice["gender"],
            "source_type": "preset",
            "locale": voice["locale"],
        }
        for voice in KOKORO_VOICES
    ]


def resolve_voice(voice_id: str | None = None) -> dict:
    normalized = str(voice_id or "").strip() or DEFAULT_VOICE_ID
    voice = VOICE_MAP.get(normalized)
    if voice is None:
        raise ValueError(f"Unknown voice_id: {normalized}")

    return {
        "id": voice["id"],
        "name": voice["name"],
        "source_type": "preset",
        "voice_id": voice["id"],
        "pipeline": voice["pipeline"],
    }
