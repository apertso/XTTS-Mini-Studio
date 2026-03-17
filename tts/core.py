from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

import numpy as np
import torch
from scipy.io import wavfile

from .config import (
    DEFAULT_CHUNK_LENGTH,
    MAX_RMS_GAIN,
    MIN_RMS_GAIN,
    MODEL_DIR,
    MODEL_DIR_ENV_VAR,
    READING_MODE_DEFAULT,
    READING_PROFILES,
    STREAM_CROSSFADE_MS,
)
from .voices import resolve_voice


SENTENCE_END_PATTERN = re.compile("[.!?\u2026][\"')\\]]*$")

_RUNTIME: Optional[Tuple[Any, Any]] = None

REQUIRED_MODEL_FILES = {
    "config": "config.json",
    "checkpoint": "model.pth",
    "vocab": "vocab.json",
    "speakers": "speakers_xtts.pth",
}


def format_log_preview(text: str, limit: int = 50) -> str:
    preview = text[:limit]
    if len(text) > limit:
        preview += "..."
    return preview.encode("ascii", errors="backslashreplace").decode("ascii")


def resolve_model_paths(model_dir: Path) -> dict[str, Path]:
    resolved = model_dir.resolve()
    paths = {
        key: resolved / file_name for key, file_name in REQUIRED_MODEL_FILES.items()
    }
    missing = [path.name for path in paths.values() if not path.exists()]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise FileNotFoundError(
            "XTTS model directory is missing required files: "
            f"{missing_list}. Checked: {resolved}. "
            f"Set {MODEL_DIR_ENV_VAR} to a valid XTTS model directory."
        )
    return paths


def _load_runtime() -> Tuple[Any, Any]:
    model_paths = resolve_model_paths(MODEL_DIR)

    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    print("Loading XTTS-v2 model...")
    config_path = model_paths["config"]

    xtts_config = XttsConfig()
    xtts_config.load_json(str(config_path))

    model = Xtts(xtts_config)
    model.load_checkpoint(
        config=xtts_config,
        checkpoint_path=str(model_paths["checkpoint"]),
        vocab_path=str(model_paths["vocab"]),
        speaker_file_path=str(model_paths["speakers"]),
        eval=True,
    )

    if torch.cuda.is_available():
        print(f"Using CUDA GPU: {torch.cuda.get_device_name(0)}")
        model = model.cuda()
        print("Using float32 precision (required for TTS inference)")
    else:
        print("CUDA not available, using CPU")

    model.eval()
    print("Model loaded!")
    return model, xtts_config


def get_runtime() -> Tuple[Any, Any]:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = _load_runtime()
    return _RUNTIME


def get_sample_rate() -> int:
    _, xtts_config = get_runtime()
    return int(xtts_config.audio.sample_rate)


def normalize_language_code(language: str) -> str:
    lang = (language or "en").strip().lower()
    if not lang:
        return "en"
    if lang == "zh-cn":
        return "zh"
    return lang.split("-")[0]


def resolve_reading_profile(reading_mode: Optional[str]) -> dict:
    mode = (reading_mode or READING_MODE_DEFAULT).strip().lower()
    profile = READING_PROFILES.get(mode)
    if profile is None:
        available = ", ".join(sorted(READING_PROFILES.keys()))
        raise ValueError(f"Invalid reading_mode: {reading_mode}. Expected one of: {available}")

    return {
        "mode": mode,
        "synthesis_kwargs": dict(profile["synthesis_kwargs"]),
        "chunk_limit_adjust": int(profile["chunk_limit_adjust"]),
        "inter_chunk_pause_ms": int(profile["inter_chunk_pause_ms"]),
    }


def resolve_chunk_length(language: str, chunk_limit_adjust: int = 0) -> int:
    _ = language
    _ = chunk_limit_adjust
    return DEFAULT_CHUNK_LENGTH


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


def extract_audio_array(outputs) -> np.ndarray:
    if isinstance(outputs, dict):
        wav = outputs["wav"]
        audio = wav.cpu().numpy() if hasattr(wav, "cpu") else wav
    elif hasattr(outputs, "cpu"):
        audio = outputs.cpu().numpy()
    else:
        audio = outputs

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    return audio.astype(np.float32)


def synthesize_chunk(
    chunk: str, language: str, voice_selection: dict, synthesis_kwargs: dict
) -> np.ndarray:
    model, xtts_config = get_runtime()
    outputs = model.synthesize(
        text=chunk,
        config=xtts_config,
        speaker_wav=voice_selection["speaker_wav"],
        speaker_id=voice_selection["speaker_id"],
        language=language,
        **synthesis_kwargs,
    )
    return extract_audio_array(outputs)


def generate_audio_chunks(
    text_chunks: List[str], language: str, voice_selection: dict, reading_profile: dict
) -> Iterator[bytes]:
    sample_rate = get_sample_rate()
    overlap_samples = int(sample_rate * STREAM_CROSSFADE_MS / 1000)
    fade_samples = int(sample_rate * 0.01)
    synthesis_kwargs = reading_profile["synthesis_kwargs"]
    inter_chunk_pause_ms = int(reading_profile["inter_chunk_pause_ms"])
    inter_chunk_pause_bytes = create_silence_bytes(inter_chunk_pause_ms, sample_rate)

    if len(text_chunks) == 0:
        return

    print(
        f"Using {voice_selection['source_type']} voice: "
        f"{voice_selection['id']} ({voice_selection['name']}), mode={reading_profile['mode']}"
    )

    pending_audio: Optional[np.ndarray] = None
    pending_text_chunk: Optional[str] = None

    with torch.inference_mode():
        for i, chunk in enumerate(text_chunks):
            print(f"Generating chunk {i + 1}/{len(text_chunks)}")
            audio_float = np.clip(
                synthesize_chunk(chunk, language, voice_selection, synthesis_kwargs), -1.0, 1.0
            ).astype(np.float32)
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
    text: str, voice_id: Optional[str], language: str, reading_mode: Optional[str]
) -> Tuple[List[str], str, dict, dict]:
    text = (text or "").strip()
    if not text:
        raise ValueError("No text provided")

    normalized_language = normalize_language_code(language)
    voice_selection = resolve_voice(voice_id)
    reading_profile = resolve_reading_profile(reading_mode)

    chunk_limit = resolve_chunk_length(
        normalized_language, chunk_limit_adjust=reading_profile["chunk_limit_adjust"]
    )
    text_chunks = split_text(text, max_length=chunk_limit)
    if len(text_chunks) == 0:
        raise ValueError("No valid text provided")

    print(
        f"Total chunks: {len(text_chunks)}, chunk_limit={chunk_limit}, "
        f"language={normalized_language}, mode={reading_profile['mode']}"
    )
    return text_chunks, normalized_language, voice_selection, reading_profile


def generate_tts(
    text: str,
    voice_id: Optional[str] = None,
    language: str = "en",
    reading_mode: Optional[str] = None,
    streaming: bool = False,
):
    text_chunks, normalized_language, voice_selection, reading_profile = _prepare_generation(
        text=text,
        voice_id=voice_id,
        language=language,
        reading_mode=reading_mode,
    )
    total_chunks = len(text_chunks)

    if streaming:
        def _stream() -> Iterator[Tuple[int, int, bytes]]:
            for i, audio_bytes in enumerate(
                generate_audio_chunks(
                    text_chunks=text_chunks,
                    language=normalized_language,
                    voice_selection=voice_selection,
                    reading_profile=reading_profile,
                )
            ):
                yield i, total_chunks, audio_bytes

        return _stream()

    audio_chunks = []
    for audio_bytes in generate_audio_chunks(
        text_chunks=text_chunks,
        language=normalized_language,
        voice_selection=voice_selection,
        reading_profile=reading_profile,
    ):
        if audio_bytes:
            audio_chunks.append(audio_bytes)

    if not audio_chunks:
        raise RuntimeError("Generation failed: no audio chunks were produced")

    final_audio = np.frombuffer(b"".join(audio_chunks), dtype=np.int16)
    buffer = io.BytesIO()
    wavfile.write(buffer, get_sample_rate(), final_audio)
    return buffer.getvalue()
