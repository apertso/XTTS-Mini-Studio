from __future__ import annotations

import base64
from typing import Any, Dict

from .config import READING_MODE_DEFAULT, configure_stdio
from .core import generate_tts


configure_stdio()


def runpod_handler(job: Dict[str, Any]) -> Dict[str, str]:
    payload = (job or {}).get("input") or {}
    text = payload.get("text", "")
    voice_id = payload.get("voice_id")
    language = payload.get("language", "en")
    reading_mode = payload.get("reading_mode", READING_MODE_DEFAULT)

    if not text:
        return {"error": "No text provided"}

    try:
        wav_bytes = generate_tts(
            text=text,
            voice_id=voice_id,
            language=language,
            reading_mode=reading_mode,
            streaming=False,
        )
    except Exception as exc:
        return {"error": str(exc)}

    return {"audio_base64": base64.b64encode(wav_bytes).decode("utf-8")}


handler = runpod_handler


def start_runpod() -> None:
    import runpod

    runpod.serverless.start({"handler": runpod_handler})
