from __future__ import annotations

import io
import json
import struct
import traceback

from flask import Flask, Response, jsonify, request, send_file

from .config import FRONTEND_DIR, TTS_HOST, TTS_PORT, configure_stdio
from .core import format_log_preview, generate_tts, get_sample_rate
from .voices import REFERENCE_VOICES, list_available_voices


configure_stdio()

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="/frontend")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def wrap_chunk_with_metadata(chunk_index: int, total_chunks: int, audio_bytes: bytes) -> bytes:
    metadata = json.dumps(
        {"c": chunk_index, "t": total_chunks, "s": len(audio_bytes)}
    ).encode("utf-8")
    return struct.pack("<I", len(metadata)) + metadata + audio_bytes


@app.route("/")
def index():
    return send_file(FRONTEND_DIR / "index.html")


@app.route("/api/voices", methods=["GET"])
def get_voices():
    return jsonify({"voices": list_available_voices()})


@app.route("/tts", methods=["POST"])
def text_to_speech():
    data = request.json or {}
    text = data.get("text", "")
    language = data.get("language", "ru")
    voice_id = data.get("voice_id") or None
    reading_mode = data.get("reading_mode")

    if not text:
        return {"error": "No text provided"}, 400

    print(
        f"TTS request: text={format_log_preview(text)}, "
        f"language={language}, voice_id={voice_id}, reading_mode={reading_mode or 'default'}"
    )

    try:
        chunk_stream = generate_tts(
            text=text,
            voice_id=voice_id,
            language=language,
            reading_mode=reading_mode,
            streaming=True,
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except Exception as exc:
        print(f"TTS endpoint setup error: {exc}")
        traceback.print_exc()
        return {"error": str(exc)}, 500

    sample_rate = get_sample_rate()
    print(f"Sample rate: {sample_rate}")

    def generate():
        try:
            for chunk_index, total_chunks, audio_bytes in chunk_stream:
                yield wrap_chunk_with_metadata(chunk_index, total_chunks, audio_bytes)
        except Exception as exc:
            print(f"Streaming error: {exc}")
            traceback.print_exc()
            raise

    return Response(
        generate(),
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="speech.pcm"',
            "Cache-Control": "no-cache",
            "X-Audio-Sample-Rate": str(sample_rate),
            "X-Audio-Format": "raw-pcm-int16",
        },
    )


@app.route("/tts/download", methods=["POST"])
def text_to_speech_download():
    data = request.json or {}
    text = data.get("text", "")
    language = data.get("language", "ru")
    voice_id = data.get("voice_id") or None
    reading_mode = data.get("reading_mode")

    if not text:
        return {"error": "No text provided"}, 400

    try:
        wav_bytes = generate_tts(
            text=text,
            voice_id=voice_id,
            language=language,
            reading_mode=reading_mode,
            streaming=False,
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except RuntimeError as exc:
        return {"error": str(exc)}, 500
    except Exception as exc:
        return {"error": f"Generation failed: {exc}"}, 500

    buffer = io.BytesIO(wav_bytes)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="audio/wav",
        as_attachment=True,
        download_name="speech.wav",
    )


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "model": "xtts_v2",
        "streaming": True,
        "reference_voices": len(REFERENCE_VOICES),
    }


def start_flask() -> None:
    app.run(host=TTS_HOST, port=TTS_PORT, debug=False, threaded=True)

