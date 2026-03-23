from __future__ import annotations

import io
import re
import threading
from typing import Any, Callable, Iterator, List, Optional, Tuple

import numpy as np
from scipy.io import wavfile

from .config import (
    DEFAULT_CHUNK_LENGTH,
    DEFAULT_INTER_CHUNK_PAUSE_MS,
    DEFAULT_SYNTHESIS_KWARGS,
    MAX_RMS_GAIN,
    MAX_TEXT_CHARACTERS,
    MIN_RMS_GAIN,
    MODEL_ID,
    STREAM_CROSSFADE_MS,
    TTS_DEVICE,
    TTS_DEVICE_SETTING,
    normalize_language_code,
)
from .voices import resolve_voice


SENTENCE_END_PATTERN = re.compile("[.!?\u2026][\"')\\]]*$")

_RUNTIME: Optional[dict[str, Any]] = None
_RUNTIME_LOCK = threading.Lock()
ProgressCallback = Callable[[int, int], None]


class GenerationCancelledError(RuntimeError):
    """Raised when generation is cancelled via cooperative cancellation signal."""


def format_log_preview(text: str, limit: int = 50) -> str:
    preview = text[:limit]
    if len(text) > limit:
        preview += "..."
    return preview.encode("ascii", errors="backslashreplace").decode("ascii")


def _load_runtime() -> dict[str, Any]:
    from kokoro import KPipeline
    import torch

    if TTS_DEVICE == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "TTS_DEVICE is set to 'cuda' but torch.cuda.is_available() is False. "
            "Install CUDA-enabled torch or switch TTS_DEVICE to 'auto'/'cpu'."
        )

    print(
        "Loading Kokoro runtime "
        f"(MODEL_ID={MODEL_ID}, requested_device={TTS_DEVICE_SETTING}, "
        f"torch={torch.__version__}, torch_cuda={torch.version.cuda}, "
        f"cuda_available={torch.cuda.is_available()})"
    )
    pipelines = {
        "a": KPipeline(lang_code="a", repo_id=MODEL_ID, device=TTS_DEVICE),
        "b": KPipeline(lang_code="b", repo_id=MODEL_ID, device=TTS_DEVICE),
    }
    effective_devices = {
        key: str(getattr(getattr(pipeline, "model", None), "device", "unknown"))
        for key, pipeline in pipelines.items()
    }
    effective_device_label = ", ".join(
        f"{key}:{device}" for key, device in sorted(effective_devices.items())
    )
    runtime = {
        "pipelines": pipelines,
        "sample_rate": 24000,
        "model_id": MODEL_ID,
        "requested_device": TTS_DEVICE_SETTING,
        "effective_devices": effective_devices,
    }
    print(f"Kokoro runtime loaded. effective_devices={effective_device_label}")
    return runtime


def get_runtime() -> dict[str, Any]:
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME

    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = _load_runtime()

    assert _RUNTIME is not None
    return _RUNTIME


def get_sample_rate() -> int:
    runtime = get_runtime()
    return int(runtime["sample_rate"])


def resolve_chunk_length(_language: str) -> int:
    return max(1, int(DEFAULT_CHUNK_LENGTH))


def split_long_sentence(sentence: str, max_length: int) -> List[str]:
    sentence = sentence.strip()
    if not sentence:
        return []
    if len(sentence) <= max_length:
        return [sentence]

    parts: List[str] = []
    remaining = sentence

    while len(remaining) > max_length:
        window = remaining[: max_length + 1]
        split_pos = -1

        for match in re.finditer(r"[,;:)\]\-]\s+|\s+", window):
            if match.start() > 0:
                split_pos = match.start()

        if split_pos <= 0:
            split_pos = max_length

        piece = remaining[:split_pos].strip()
        if not piece:
            piece = remaining[:max_length].strip()
            split_pos = max_length

        parts.append(piece)
        remaining = remaining[split_pos:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def split_text(text: str, max_length: int) -> List[str]:
    lines = text.split("\n")
    sentences: List[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split("(?<=[.!?\u2026])\\s+", line)
        for part in parts:
            part = part.strip()
            if part:
                sentences.extend(split_long_sentence(part, max_length))

    chunks: List[str] = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) == 0:
            current_chunk = sentence
        elif len(current_chunk) + len(sentence) + 1 <= max_length:
            current_chunk += " " + sentence
        else:
            chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def apply_edge_fade(
    audio: np.ndarray, fade_samples: int, fade_in: bool, fade_out: bool
) -> np.ndarray:
    if fade_samples <= 1 or len(audio) == 0:
        return audio

    result = audio.astype(np.float32, copy=True)
    fade_span = min(fade_samples, len(result))

    if fade_in:
        result[:fade_span] *= np.linspace(0.0, 1.0, fade_span, dtype=np.float32)
    if fade_out:
        result[-fade_span:] *= np.linspace(1.0, 0.0, fade_span, dtype=np.float32)

    return result


def crossfade_chunks(
    previous_audio: np.ndarray, current_audio: np.ndarray, overlap_samples: int
) -> Tuple[np.ndarray, np.ndarray]:
    overlap = min(overlap_samples, len(previous_audio), len(current_audio))
    if overlap <= 0:
        return previous_audio, current_audio

    previous_audio = previous_audio.astype(np.float32, copy=False)
    current_audio = current_audio.astype(np.float32, copy=False)

    previous_tail = previous_audio[-overlap:]
    current_head = current_audio[:overlap]

    previous_rms = float(np.sqrt(np.mean(previous_tail**2)) + 1e-8)
    current_rms = float(np.sqrt(np.mean(current_head**2)) + 1e-8)
    gain = float(np.clip(previous_rms / current_rms, MIN_RMS_GAIN, MAX_RMS_GAIN))
    current_adjusted = current_audio * gain

    phase = np.linspace(0.0, np.pi / 2.0, overlap, dtype=np.float32)
    fade_out = np.cos(phase)
    fade_in = np.sin(phase)
    blended = previous_tail * fade_out + current_adjusted[:overlap] * fade_in

    finalized_previous = np.concatenate([previous_audio[:-overlap], blended]).astype(
        np.float32, copy=False
    )
    remaining_current = current_adjusted[overlap:].astype(np.float32, copy=False)
    return finalized_previous, remaining_current


def float_audio_to_int16_bytes(audio: np.ndarray) -> bytes:
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def ends_with_sentence_boundary(text_chunk: str) -> bool:
    return bool(SENTENCE_END_PATTERN.search(text_chunk.strip()))


def create_silence_bytes(duration_ms: int, sample_rate: int) -> bytes:
    if duration_ms <= 0:
        return b""
    silence_samples = max(1, int(sample_rate * duration_ms / 1000))
    return np.zeros(silence_samples, dtype=np.int16).tobytes()


def extract_audio_array(audio: Any) -> np.ndarray:
    if hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()

    audio_array = np.asarray(audio, dtype=np.float32)
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)
    return audio_array.astype(np.float32)


def _synthesize_chunk_once(chunk: str, voice_selection: dict) -> np.ndarray:
    runtime = get_runtime()
    pipeline_key = voice_selection["pipeline"]
    pipeline = runtime["pipelines"].get(pipeline_key)
    if pipeline is None:
        raise RuntimeError(f"Pipeline '{pipeline_key}' is not initialized for voice_id={voice_selection['id']}")

    voice_id = voice_selection["voice_id"]
    speed = float(DEFAULT_SYNTHESIS_KWARGS.get("speed", 1.0))

    parts: list[np.ndarray] = []
    generator = pipeline(chunk, voice=voice_id, speed=speed)
    for _gs, _ps, audio in generator:
        normalized = extract_audio_array(audio)
        if normalized.size > 0:
            parts.append(normalized)

    if not parts:
        return np.zeros(0, dtype=np.float32)

    return np.concatenate(parts).astype(np.float32, copy=False)


def synthesize_chunk(chunk: str, voice_selection: dict) -> np.ndarray:
    return _synthesize_chunk_once(chunk=chunk, voice_selection=voice_selection)


def generate_audio_chunks(
    text_chunks: List[str],
    language: str,
    voice_selection: dict,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[bytes]:
    _ = language  # language is validated at preparation stage and fixed to English in v1.

    sample_rate = get_sample_rate()
    overlap_samples = int(sample_rate * STREAM_CROSSFADE_MS / 1000)
    fade_samples = int(sample_rate * 0.01)
    inter_chunk_pause_ms = int(DEFAULT_INTER_CHUNK_PAUSE_MS)
    inter_chunk_pause_bytes = create_silence_bytes(inter_chunk_pause_ms, sample_rate)

    if len(text_chunks) == 0:
        return

    total_chunks = len(text_chunks)

    print(
        f"Using Kokoro voice: {voice_selection['id']} ({voice_selection['name']})"
    )

    pending_audio: Optional[np.ndarray] = None
    pending_text_chunk: Optional[str] = None

    for i, chunk in enumerate(text_chunks):
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelledError("Generation was cancelled.")

        print(f"Generating chunk {i + 1}/{len(text_chunks)}")
        audio_float = np.clip(
            synthesize_chunk(chunk=chunk, voice_selection=voice_selection),
            -1.0,
            1.0,
        ).astype(np.float32)

        if progress_callback is not None:
            progress_callback(i + 1, total_chunks)

        if len(audio_float) == 0:
            continue

        if pending_audio is None:
            pending_audio = apply_edge_fade(
                audio_float, fade_samples, fade_in=True, fade_out=False
            )
            pending_text_chunk = chunk
            continue

        boundary_has_sentence_pause = bool(
            inter_chunk_pause_bytes
            and pending_text_chunk
            and ends_with_sentence_boundary(pending_text_chunk)
        )

        if boundary_has_sentence_pause:
            finalized_audio = apply_edge_fade(
                pending_audio, fade_samples, fade_in=False, fade_out=True
            )
            if len(finalized_audio) > 0:
                yield float_audio_to_int16_bytes(finalized_audio) + inter_chunk_pause_bytes
            pending_audio = apply_edge_fade(
                audio_float, fade_samples, fade_in=True, fade_out=False
            )
        else:
            finalized_audio, pending_audio = crossfade_chunks(
                pending_audio, audio_float, overlap_samples
            )
            if len(finalized_audio) > 0:
                yield float_audio_to_int16_bytes(finalized_audio)

        pending_text_chunk = chunk

    if pending_audio is not None and len(pending_audio) > 0:
        pending_audio = apply_edge_fade(pending_audio, fade_samples, fade_in=False, fade_out=True)
        yield float_audio_to_int16_bytes(pending_audio)


def _prepare_generation(
    text: str, voice_id: Optional[str], language: str
) -> Tuple[List[str], str, dict]:
    text = (text or "").strip()
    if not text:
        raise ValueError("No text provided")
    if len(text) > MAX_TEXT_CHARACTERS:
        raise ValueError(
            f"Text exceeds maximum length: {MAX_TEXT_CHARACTERS} characters "
            f"(got {len(text)})."
        )

    normalized_language = normalize_language_code(language)
    voice_selection = resolve_voice(voice_id)

    chunk_limit = resolve_chunk_length(normalized_language)
    text_chunks = split_text(text, max_length=chunk_limit)
    if len(text_chunks) == 0:
        raise ValueError("No valid text provided")

    print(
        f"Total chunks: {len(text_chunks)}, chunk_limit={chunk_limit}, "
        f"language={normalized_language}"
    )
    return text_chunks, normalized_language, voice_selection


def generate_tts(
    text: str,
    voice_id: Optional[str] = None,
    language: str = "en",
    progress_callback: Optional[ProgressCallback] = None,
    cancel_event: threading.Event | None = None,
):
    text_chunks, normalized_language, voice_selection = _prepare_generation(
        text=text,
        voice_id=voice_id,
        language=language,
    )

    audio_chunks = []
    for audio_bytes in generate_audio_chunks(
        text_chunks=text_chunks,
        language=normalized_language,
        voice_selection=voice_selection,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    ):
        if audio_bytes:
            audio_chunks.append(audio_bytes)

    if not audio_chunks:
        raise RuntimeError("Generation failed: no audio chunks were produced")

    final_audio = np.frombuffer(b"".join(audio_chunks), dtype=np.int16)
    buffer = io.BytesIO()
    wavfile.write(buffer, get_sample_rate(), final_audio)
    return buffer.getvalue()
