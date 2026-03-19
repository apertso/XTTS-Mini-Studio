from __future__ import annotations

import io
import threading
import time
import traceback
import uuid
from typing import Any, Optional

from flask import Flask, jsonify, request, send_file

from .config import (
    LOCAL_JOB_MAX_TERMINAL,
    LOCAL_JOB_TTL_SECONDS,
    MAX_TEXT_CHARACTERS,
    TTS_HOST,
    TTS_PORT,
    configure_stdio,
)
from .core import (
    GenerationCancelledError,
    format_log_preview,
    generate_tts,
)
from .voices import REFERENCE_VOICES, list_available_voices


configure_stdio()

app = Flask(__name__)

TERMINAL_JOB_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


class JobManager:
    def __init__(self, ttl_seconds: int, max_terminal: int):
        self._ttl_seconds = int(ttl_seconds)
        self._max_terminal = int(max_terminal)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _serialize_job_locked(self, job: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": job["id"],
            "status": job["status"],
            "created_at": int(job["created_at"] * 1000),
            "updated_at": int(job["updated_at"] * 1000),
            "processed_chunks": int(job["processed_chunks"]),
            "total_chunks": (
                int(job["total_chunks"])
                if job["total_chunks"] is not None
                else None
            ),
            "cancel_requested": bool(job["cancel_requested"]),
        }

        if job["status"] == "COMPLETED" and job["wav_bytes"] is not None:
            payload["output"] = {
                "audio_ready": True,
                "audio_bytes": len(job["wav_bytes"]),
                "processed_chunks": int(job["processed_chunks"]),
                "total_chunks": (
                    int(job["total_chunks"])
                    if job["total_chunks"] is not None
                    else None
                ),
            }
        if job["error"]:
            payload["error"] = str(job["error"])
        return payload

    def _cleanup_locked(self, now: float) -> None:
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if job["status"] in TERMINAL_JOB_STATUSES
            and (now - float(job["updated_at"])) > self._ttl_seconds
        ]
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)

        terminal_jobs = [
            job
            for job in self._jobs.values()
            if job["status"] in TERMINAL_JOB_STATUSES
        ]
        overflow = len(terminal_jobs) - self._max_terminal
        if overflow <= 0:
            return

        terminal_jobs.sort(key=lambda item: float(item["updated_at"]))
        for job in terminal_jobs[:overflow]:
            self._jobs.pop(job["id"], None)

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "IN_QUEUE",
            "created_at": now,
            "updated_at": now,
            "payload": dict(payload),
            "cancel_event": threading.Event(),
            "cancel_requested": False,
            "processed_chunks": 0,
            "total_chunks": None,
            "wav_bytes": None,
            "error": None,
        }

        with self._lock:
            self._cleanup_locked(now)
            self._jobs[job_id] = job
            serialized = self._serialize_job_locked(job)

        worker = threading.Thread(
            target=self._run_job,
            args=(job_id,),
            daemon=True,
        )
        worker.start()
        return serialized

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job["status"] in TERMINAL_JOB_STATUSES:
                return
            job["status"] = "IN_PROGRESS"
            job["updated_at"] = time.time()
            payload = dict(job["payload"])
            cancel_event: threading.Event = job["cancel_event"]

        try:
            def progress_callback(processed_chunks: int, total_chunks: int) -> None:
                with self._lock:
                    tracked = self._jobs.get(job_id)
                    if tracked is None:
                        return
                    if tracked["status"] in TERMINAL_JOB_STATUSES:
                        return
                    tracked["processed_chunks"] = max(0, int(processed_chunks))
                    tracked["total_chunks"] = max(0, int(total_chunks))
                    tracked["updated_at"] = time.time()

            wav_bytes = generate_tts(
                text=payload.get("text", ""),
                voice_id=payload.get("voice_id"),
                language=payload.get("language", "en"),
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )

            with self._lock:
                tracked = self._jobs.get(job_id)
                if tracked is None:
                    return
                if cancel_event.is_set():
                    tracked["status"] = "CANCELLED"
                    tracked["wav_bytes"] = None
                else:
                    tracked["status"] = "COMPLETED"
                    tracked["wav_bytes"] = wav_bytes
                    if tracked["total_chunks"] is not None:
                        tracked["processed_chunks"] = max(
                            int(tracked["processed_chunks"]),
                            int(tracked["total_chunks"]),
                        )
                tracked["updated_at"] = time.time()
                self._cleanup_locked(tracked["updated_at"])
            return
        except GenerationCancelledError:
            error_message: Optional[str] = None
            final_status = "CANCELLED"
        except ValueError as exc:
            error_message = str(exc)
            final_status = "FAILED"
        except Exception as exc:
            print(f"Local TTS job failed ({job_id}): {exc}")
            traceback.print_exc()
            error_message = str(exc)
            final_status = "FAILED"

        with self._lock:
            tracked = self._jobs.get(job_id)
            if tracked is None:
                return
            tracked["status"] = final_status
            tracked["error"] = error_message
            tracked["wav_bytes"] = None
            tracked["updated_at"] = time.time()
            self._cleanup_locked(tracked["updated_at"])

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return self._serialize_job_locked(job)

    def cancel_job(self, job_id: str) -> Optional[dict[str, Any]]:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job["status"] not in TERMINAL_JOB_STATUSES:
                job["cancel_requested"] = True
                job["cancel_event"].set()
                if job["status"] == "IN_QUEUE":
                    job["status"] = "CANCELLED"
                job["updated_at"] = now

            return self._serialize_job_locked(job)

    def get_audio_bytes(self, job_id: str) -> tuple[str, Optional[bytes], Optional[str]] | None:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job["status"], job["wav_bytes"], job["error"]


JOB_MANAGER = JobManager(
    ttl_seconds=LOCAL_JOB_TTL_SECONDS,
    max_terminal=LOCAL_JOB_MAX_TERMINAL,
)


def _read_json_object() -> tuple[dict[str, Any] | None, Optional[str]]:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}, None
    if not isinstance(payload, dict):
        return None, "JSON body must be an object."
    return payload, None


def _validate_job_payload(data: dict[str, Any]) -> tuple[dict[str, Any] | None, Optional[str]]:
    if "reading_mode" in data:
        return None, "Field 'reading_mode' is no longer supported; remove it."

    text = str(data.get("text", "")).strip()
    if not text:
        return None, "No text provided"
    if len(text) > MAX_TEXT_CHARACTERS:
        return None, (
            f"Text exceeds maximum length: {MAX_TEXT_CHARACTERS} characters "
            f"(got {len(text)})."
        )

    language = str(data.get("language", "en")).strip() or "en"
    voice_value = data.get("voice_id")
    voice_id = str(voice_value).strip() if voice_value is not None else None
    if voice_id == "":
        voice_id = None

    return {
        "text": text,
        "language": language,
        "voice_id": voice_id,
    }, None


@app.route("/api/voices", methods=["GET"])
def get_voices():
    return jsonify({"voices": list_available_voices()})


@app.route("/tts/jobs", methods=["POST"])
def submit_tts_job():
    data, parse_error = _read_json_object()
    if parse_error:
        return {"error": parse_error}, 400
    assert data is not None

    payload, validation_error = _validate_job_payload(data)
    if validation_error:
        return {"error": validation_error}, 400
    assert payload is not None

    print(
        "TTS async job submit: "
        f"text={format_log_preview(payload['text'])}, "
        f"language={payload['language']}, "
        f"voice_id={payload['voice_id']}"
    )

    job = JOB_MANAGER.create_job(payload)
    return jsonify(job), 202


@app.route("/tts/jobs/<job_id>", methods=["GET"])
def get_tts_job(job_id: str):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return {"error": "Job id is required."}, 400

    job = JOB_MANAGER.get_job(normalized_job_id)
    if job is None:
        return {"error": "Job not found."}, 404
    return jsonify(job)


@app.route("/tts/jobs/<job_id>/cancel", methods=["POST"])
def cancel_tts_job(job_id: str):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return {"error": "Job id is required."}, 400

    job = JOB_MANAGER.cancel_job(normalized_job_id)
    if job is None:
        return {"error": "Job not found."}, 404
    return jsonify(job)


@app.route("/tts/jobs/<job_id>/audio", methods=["GET"])
def get_tts_job_audio(job_id: str):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return {"error": "Job id is required."}, 400

    audio_state = JOB_MANAGER.get_audio_bytes(normalized_job_id)
    if audio_state is None:
        return {"error": "Job not found."}, 404

    status, wav_bytes, error = audio_state
    if status != "COMPLETED":
        return {
            "error": (
                f"Audio is not available. Job status: {status}."
                if not error
                else f"Audio is not available. Job status: {status}. Error: {error}"
            )
        }, 409

    if not wav_bytes:
        return {"error": "Completed job has no audio bytes."}, 500

    buffer = io.BytesIO(wav_bytes)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="audio/wav",
        as_attachment=True,
        download_name=f"{normalized_job_id}.wav",
    )


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "model": "xtts_v2",
        "job_api": True,
        "reference_voices": len(REFERENCE_VOICES),
    }


def start_flask() -> None:
    app.run(host=TTS_HOST, port=TTS_PORT, debug=False, threaded=True)
