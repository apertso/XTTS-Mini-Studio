from __future__ import annotations

import base64
import os
import re
import uuid
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from .config import configure_stdio
from .core import generate_tts


configure_stdio()

DEFAULT_MAX_INLINE_AUDIO_BYTES = 6_500_000
DEFAULT_UPLOAD_PREFIX = "kokoro-audio"
DEFAULT_UPLOAD_BUCKET_NAME = ""


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


MAX_INLINE_AUDIO_BYTES = _read_int_env(
    "RUNPOD_INLINE_AUDIO_MAX_BYTES", DEFAULT_MAX_INLINE_AUDIO_BYTES
)
UPLOAD_PREFIX = (
    os.environ.get("RUNPOD_AUDIO_UPLOAD_PREFIX", DEFAULT_UPLOAD_PREFIX).strip()
    or DEFAULT_UPLOAD_PREFIX
)
UPLOAD_BUCKET_NAME = (
    os.environ.get("RUNPOD_AUDIO_BUCKET_NAME", DEFAULT_UPLOAD_BUCKET_NAME).strip()
    or None
)


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_job_slug(job: Dict[str, Any]) -> str:
    raw_id = str(job.get("id") or "job")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw_id).strip("-")
    return slug or "job"


def _upload_audio(job: Dict[str, Any], wav_bytes: bytes) -> str:
    try:
        from runpod.serverless.utils import rp_upload
    except Exception as exc:
        raise RuntimeError(
            "RunPod upload utility is unavailable. Install runpod+boto3 and configure BUCKET_* env vars."
        ) from exc

    file_name = f"{_safe_job_slug(job)}-{uuid.uuid4().hex[:8]}.wav"
    audio_url = rp_upload.upload_in_memory_object(
        file_name=file_name,
        file_data=wav_bytes,
        bucket_name=UPLOAD_BUCKET_NAME,
        prefix=UPLOAD_PREFIX,
    )

    if not isinstance(audio_url, str) or not _is_http_url(audio_url):
        raise RuntimeError(
            "Upload fallback returned a local path. Configure BUCKET_ENDPOINT_URL, "
            "BUCKET_ACCESS_KEY_ID, BUCKET_SECRET_ACCESS_KEY, and RUNPOD_AUDIO_BUCKET_NAME "
            "for reachable audio URLs."
        )

    return audio_url


def _build_progress_reporter(
    job: Dict[str, Any],
) -> Optional[Callable[[int, int], None]]:
    try:
        import runpod
    except Exception:
        return None

    progress_update = getattr(getattr(runpod, "serverless", None), "progress_update", None)
    if not callable(progress_update):
        return None

    updates_enabled = True

    def _report(processed_chunks: int, total_chunks: int) -> None:
        nonlocal updates_enabled
        if not updates_enabled:
            return

        safe_processed = max(0, int(processed_chunks))
        safe_total = max(safe_processed, int(total_chunks))
        payload = {
            "progress": {
                "processed_chunks": safe_processed,
                "total_chunks": safe_total,
            },
            "processed_chunks": safe_processed,
            "total_chunks": safe_total,
        }

        try:
            progress_update(job, payload)
        except Exception as exc:
            updates_enabled = False
            print(f"RunPod progress updates disabled: {exc}")

    return _report


def runpod_handler(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = (job or {}).get("input") or {}
    if "reading_mode" in payload:
        return {"error": "Field 'reading_mode' is no longer supported; remove it."}

    text = payload.get("text", "")
    voice_id = payload.get("voice_id")
    language = payload.get("language", "en")

    if not text:
        return {"error": "No text provided"}

    progress_reporter = _build_progress_reporter(job or {})

    try:
        wav_bytes = generate_tts(
            text=text,
            voice_id=voice_id,
            language=language,
            progress_callback=progress_reporter,
        )
    except Exception as exc:
        return {"error": str(exc)}

    audio_size = len(wav_bytes)
    if audio_size <= MAX_INLINE_AUDIO_BYTES:
        return {
            "audio_base64": base64.b64encode(wav_bytes).decode("utf-8"),
            "audio_bytes": audio_size,
            "delivery": "inline_base64",
        }

    try:
        audio_url = _upload_audio(job or {}, wav_bytes)
    except Exception as exc:
        return {
            "error": (
                "Generated audio is too large for inline RunPod results "
                f"({audio_size} bytes > {MAX_INLINE_AUDIO_BYTES}). "
                "Configure BUCKET_ENDPOINT_URL, BUCKET_ACCESS_KEY_ID, "
                "BUCKET_SECRET_ACCESS_KEY, RUNPOD_AUDIO_BUCKET_NAME, and boto3 "
                "for audio_url fallback. "
                f"Upload failed: {exc}"
            ),
            "audio_bytes": audio_size,
            "max_inline_audio_bytes": MAX_INLINE_AUDIO_BYTES,
        }

    return {
        "audio_url": audio_url,
        "audio_bytes": audio_size,
        "delivery": "bucket_url",
    }


handler = runpod_handler


def start_runpod() -> None:
    import runpod

    runpod.serverless.start({"handler": runpod_handler})
