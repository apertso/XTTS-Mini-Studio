from __future__ import annotations

from contextlib import nullcontext
import io
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Tuple

from huggingface_hub import snapshot_download
from huggingface_hub.utils import (
    EntryNotFoundError,
    GatedRepoError,
    HfHubHTTPError,
    LocalEntryNotFoundError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
import numpy as np
import torch
from scipy.io import wavfile

from .config import (
    DEFAULT_INTER_CHUNK_PAUSE_MS,
    DEFAULT_CHUNK_LENGTH,
    DEFAULT_SYNTHESIS_KWARGS,
    HF_HOME,
    HF_HOME_ENV_VAR,
    HUGGINGFACE_HUB_CACHE,
    HUGGINGFACE_HUB_CACHE_ENV_VAR,
    LEGACY_MODEL_DIR_ENV_VAR,
    MAX_RMS_GAIN,
    MAX_TEXT_CHARACTERS,
    MODE,
    MIN_RMS_GAIN,
    MODEL_DIR_SOURCE,
    MODEL_DIR,
    MODEL_DIR_ENV_VAR,
    MODEL_ID,
    MODEL_ID_ENV_VAR,
    PRECISION_FP16,
    REQUESTED_PRECISION,
    STREAM_CROSSFADE_MS,
    TOKENIZER_CHAR_LIMITS,
    resolve_effective_precision,
    validate_mode,
)
from .voices import resolve_voice


SENTENCE_END_PATTERN = re.compile("[.!?\u2026][\"')\\]]*$")

_RUNTIME: Optional[Tuple[Any, Any]] = None
_PRECISION_STATE: Optional[dict[str, Any]] = None
_VOICE_CONDITIONING_CACHE: dict[str, tuple[Any, Any]] = {}
_VOICE_CONDITIONING_CACHE_LOCK = threading.Lock()
ProgressCallback = Callable[[int, int], None]

REQUIRED_MODEL_FILES = {
    "config": "config.json",
    "checkpoint": "model.pth",
    "vocab": "vocab.json",
    "speakers": "speakers_xtts.pth",
}
HF_ALLOW_PATTERNS = tuple(REQUIRED_MODEL_FILES.values())


class ModelResolutionError(RuntimeError):
    """Raised when XTTS model resolution through local path/cache/download fails."""


class GenerationCancelledError(RuntimeError):
    """Raised when generation is cancelled via cooperative cancellation signal."""


def format_log_preview(text: str, limit: int = 50) -> str:
    preview = text[:limit]
    if len(text) > limit:
        preview += "..."
    return preview.encode("ascii", errors="backslashreplace").decode("ascii")


def _format_path(path: Path | None) -> str:
    return str(path) if path is not None else "<unset>"


def _missing_model_files(model_dir: Path) -> list[str]:
    resolved = model_dir.resolve()
    missing = []
    for file_name in REQUIRED_MODEL_FILES.values():
        if not (resolved / file_name).exists():
            missing.append(file_name)
    return missing


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
            f"Set {MODEL_DIR_ENV_VAR} (or legacy {LEGACY_MODEL_DIR_ENV_VAR}) "
            "to a valid XTTS model directory."
        )
    return paths


def _classify_hf_error(exc: Exception) -> str:
    if isinstance(exc, GatedRepoError):
        return "auth issue"
    if isinstance(exc, HfHubHTTPError):
        status = exc.response.status_code if exc.response is not None else None
        if status in {401, 403}:
            return "auth issue"
        if status == 404:
            return "model not found"
    if isinstance(exc, (RepositoryNotFoundError, RevisionNotFoundError, EntryNotFoundError)):
        return "model not found"
    return "download failed"


def _resolve_hf_snapshot(cache_dir: Path | None, local_files_only: bool) -> Path:
    snapshot_path = snapshot_download(
        repo_id=MODEL_ID,
        cache_dir=str(cache_dir) if cache_dir is not None else None,
        local_files_only=local_files_only,
        allow_patterns=list(HF_ALLOW_PATTERNS),
    )
    return Path(snapshot_path).resolve()


def resolve_runtime_model_dir() -> Path:
    print(
        "Model environment: "
        f"{MODEL_ID_ENV_VAR}={MODEL_ID}, "
        f"{MODEL_DIR_ENV_VAR}={_format_path(MODEL_DIR)}, "
        f"{HF_HOME_ENV_VAR}={_format_path(HF_HOME)}, "
        f"{HUGGINGFACE_HUB_CACHE_ENV_VAR}={_format_path(HUGGINGFACE_HUB_CACHE)}"
    )
    if MODEL_DIR_SOURCE == LEGACY_MODEL_DIR_ENV_VAR:
        print(
            f"Model directory resolved from legacy env var {LEGACY_MODEL_DIR_ENV_VAR}; "
            f"prefer {MODEL_DIR_ENV_VAR}."
        )

    local_path_issue: str | None = None
    if MODEL_DIR is not None:
        if not MODEL_DIR.exists():
            local_path_issue = f"wrong path: local model directory does not exist ({MODEL_DIR})"
            print(f"Model directory check: {local_path_issue}")
        elif not MODEL_DIR.is_dir():
            local_path_issue = f"wrong path: local model path is not a directory ({MODEL_DIR})"
            print(f"Model directory check: {local_path_issue}")
        else:
            missing = _missing_model_files(MODEL_DIR)
            if not missing:
                print(f"Model source: local directory ({MODEL_DIR})")
                return MODEL_DIR.resolve()
            local_path_issue = (
                f"missing files: {', '.join(sorted(missing))} in {MODEL_DIR}"
            )
            print(
                "Model directory check: "
                f"{local_path_issue}. Falling back to Hugging Face cache/model download."
            )

    cache_dir = MODEL_DIR if MODEL_DIR is not None else HUGGINGFACE_HUB_CACHE
    print(
        f"Checking Hugging Face local cache for '{MODEL_ID}' "
        f"(cache_dir={_format_path(cache_dir)})"
    )
    try:
        snapshot_path = _resolve_hf_snapshot(cache_dir=cache_dir, local_files_only=True)
        print(f"Model source: Hugging Face cache (local hit) at {snapshot_path}")
    except LocalEntryNotFoundError:
        print("Hugging Face cache status: miss")
        snapshot_path = None
    except Exception as exc:
        print(
            "Hugging Face cache lookup failed; continuing with online download. "
            f"Reason: {format_log_preview(str(exc), limit=220)}"
        )
        snapshot_path = None

    if snapshot_path is None:
        print("Attempting XTTS model download from Hugging Face...")
        try:
            snapshot_path = _resolve_hf_snapshot(cache_dir=cache_dir, local_files_only=False)
            print(f"Hugging Face download status: success ({snapshot_path})")
        except Exception as exc:
            reason = _classify_hf_error(exc)
            local_issue_note = (
                f" local_issue={local_path_issue};" if local_path_issue is not None else ""
            )
            raise ModelResolutionError(
                "XTTS model resolution failed: "
                f"{reason};{local_issue_note} "
                f"model_id={MODEL_ID}; cache_dir={_format_path(cache_dir)}; "
                f"error={format_log_preview(str(exc), limit=280)}"
            ) from exc

    missing = _missing_model_files(snapshot_path)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ModelResolutionError(
            "XTTS model resolution failed: missing files; "
            f"required={missing_list}; resolved_path={snapshot_path}; "
            "check MODEL_DIR/MODEL_ID or Hugging Face cache integrity."
        )

    print(f"Final XTTS model path: {snapshot_path}")
    return snapshot_path


def _load_runtime() -> Tuple[Any, Any]:
    global _PRECISION_STATE
    resolved_model_dir = resolve_runtime_model_dir()
    model_paths = resolve_model_paths(resolved_model_dir)

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

    mode = validate_mode(MODE)
    cuda_available = torch.cuda.is_available()
    effective_precision, precision_note = resolve_effective_precision(
        mode=mode,
        requested_precision=REQUESTED_PRECISION,
        cuda_available=cuda_available,
    )
    autocast_enabled = bool(cuda_available and effective_precision == PRECISION_FP16)
    _PRECISION_STATE = {
        "mode": mode,
        "cuda_available": cuda_available,
        "requested_precision": REQUESTED_PRECISION,
        "effective_precision": effective_precision,
        "autocast_enabled": autocast_enabled,
        "runtime_fallback_triggered": False,
    }

    if cuda_available:
        print(f"Using CUDA GPU: {torch.cuda.get_device_name(0)}")
        model = model.cuda()
    else:
        print("CUDA not available, using CPU")

    print(
        "Precision policy: "
        f"requested={REQUESTED_PRECISION}, "
        f"effective={effective_precision}, "
        f"mode={mode}, "
        f"autocast={'on' if autocast_enabled else 'off'}"
    )
    if precision_note:
        print(f"Precision policy note: {precision_note}")

    model.eval()
    print("Model loaded!")
    return model, xtts_config


def get_runtime() -> Tuple[Any, Any]:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = _load_runtime()
    return _RUNTIME


def get_precision_state() -> dict[str, Any]:
    global _PRECISION_STATE
    if _PRECISION_STATE is None:
        get_runtime()
    assert _PRECISION_STATE is not None
    return _PRECISION_STATE


def _autocast_context():
    precision_state = get_precision_state()
    if precision_state["autocast_enabled"] and precision_state["cuda_available"]:
        return torch.autocast(device_type="cuda", dtype=torch.float16, enabled=True)
    return nullcontext()


def _synthesize_chunk_once(
    model: Any,
    chunk: str,
    language: str,
    conditioning: tuple[Any, Any],
    synthesis_kwargs: dict,
):
    gpt_cond_latent, speaker_embedding = conditioning
    with _autocast_context():
        return model.inference(
            text=chunk,
            language=language,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            **synthesis_kwargs,
        )


def _resolve_voice_cache_key(voice_selection: dict) -> str:
    speaker_wav = voice_selection.get("speaker_wav")
    if speaker_wav:
        return f"reference:{Path(speaker_wav).resolve()}"

    speaker_id = voice_selection.get("speaker_id")
    if speaker_id:
        return f"preset:{speaker_id}"

    raise ValueError("Invalid voice selection: missing speaker_wav/speaker_id")


def _compute_voice_conditioning(model: Any, xtts_config: Any, voice_selection: dict) -> tuple[Any, Any]:
    speaker_wav = voice_selection.get("speaker_wav")
    if speaker_wav:
        return model.get_conditioning_latents(
            audio_path=speaker_wav,
            gpt_cond_len=xtts_config.gpt_cond_len,
            gpt_cond_chunk_len=xtts_config.gpt_cond_chunk_len,
            max_ref_length=xtts_config.max_ref_len,
            sound_norm_refs=xtts_config.sound_norm_refs,
        )

    speaker_id = voice_selection.get("speaker_id")
    if not speaker_id:
        raise ValueError("Invalid voice selection: missing speaker_wav/speaker_id")

    if model.speaker_manager is None or speaker_id not in model.speaker_manager.speakers:
        raise ValueError(f"Unknown XTTS preset speaker_id: {speaker_id}")

    speaker_values = model.speaker_manager.speakers[speaker_id]
    if isinstance(speaker_values, dict):
        gpt_cond_latent = speaker_values.get("gpt_cond_latent")
        speaker_embedding = speaker_values.get("speaker_embedding")
        if gpt_cond_latent is not None and speaker_embedding is not None:
            return gpt_cond_latent, speaker_embedding

    gpt_cond_latent, speaker_embedding = speaker_values.values()
    return gpt_cond_latent, speaker_embedding


def get_voice_conditioning(model: Any, xtts_config: Any, voice_selection: dict) -> tuple[Any, Any]:
    cache_key = _resolve_voice_cache_key(voice_selection)

    with _VOICE_CONDITIONING_CACHE_LOCK:
        cached = _VOICE_CONDITIONING_CACHE.get(cache_key)

    if cached is not None:
        print(f"conditioning_cache_hit: key={cache_key}")
        return cached

    print(f"conditioning_cache_miss: key={cache_key}")
    started_at = time.perf_counter()
    computed = _compute_voice_conditioning(model, xtts_config, voice_selection)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0

    with _VOICE_CONDITIONING_CACHE_LOCK:
        cached = _VOICE_CONDITIONING_CACHE.get(cache_key)
        if cached is not None:
            print(f"conditioning_cache_race_reuse: key={cache_key}")
            return cached
        _VOICE_CONDITIONING_CACHE[cache_key] = computed

    print(f"conditioning_cache_store: key={cache_key}, prep_ms={elapsed_ms:.1f}")
    return computed


def _disable_autocast_after_runtime_error(exc: RuntimeError) -> bool:
    precision_state = get_precision_state()
    if not precision_state["autocast_enabled"]:
        return False

    precision_state["autocast_enabled"] = False
    precision_state["effective_precision"] = "fp32"
    precision_state["runtime_fallback_triggered"] = True
    print(
        "FP16 autocast failed with RuntimeError; retrying current chunk in fp32 "
        "and disabling autocast for this process."
    )
    print(f"Autocast failure reason: {format_log_preview(str(exc), limit=200)}")
    return True


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


def resolve_chunk_length(language: str) -> int:
    normalized_language = normalize_language_code(language)
    tokenizer_limit = TOKENIZER_CHAR_LIMITS.get(normalized_language)

    base_limit = DEFAULT_CHUNK_LENGTH
    if tokenizer_limit is not None:
        base_limit = min(base_limit, max(1, tokenizer_limit - 1))

    return max(1, base_limit)


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
    model: Any, chunk: str, language: str, conditioning: tuple[Any, Any], synthesis_kwargs: dict
) -> np.ndarray:
    try:
        outputs = _synthesize_chunk_once(
            model=model,
            chunk=chunk,
            language=language,
            conditioning=conditioning,
            synthesis_kwargs=synthesis_kwargs,
        )
    except RuntimeError as exc:
        if not _disable_autocast_after_runtime_error(exc):
            raise
        outputs = _synthesize_chunk_once(
            model=model,
            chunk=chunk,
            language=language,
            conditioning=conditioning,
            synthesis_kwargs=synthesis_kwargs,
        )
    return extract_audio_array(outputs)


def generate_audio_chunks(
    text_chunks: List[str],
    language: str,
    voice_selection: dict,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[bytes]:
    model, xtts_config = get_runtime()
    sample_rate = int(xtts_config.audio.sample_rate)
    overlap_samples = int(sample_rate * STREAM_CROSSFADE_MS / 1000)
    fade_samples = int(sample_rate * 0.01)
    synthesis_kwargs = dict(DEFAULT_SYNTHESIS_KWARGS)
    inter_chunk_pause_ms = int(DEFAULT_INTER_CHUNK_PAUSE_MS)
    inter_chunk_pause_bytes = create_silence_bytes(inter_chunk_pause_ms, sample_rate)
    conditioning = get_voice_conditioning(model, xtts_config, voice_selection)

    if len(text_chunks) == 0:
        return

    total_chunks = len(text_chunks)

    print(
        f"Using {voice_selection['source_type']} voice: "
        f"{voice_selection['id']} ({voice_selection['name']})"
    )

    pending_audio: Optional[np.ndarray] = None
    pending_text_chunk: Optional[str] = None

    with torch.inference_mode():
        for i, chunk in enumerate(text_chunks):
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelledError("Generation was cancelled.")
            print(f"Generating chunk {i + 1}/{len(text_chunks)}")
            audio_float = np.clip(
                synthesize_chunk(model, chunk, language, conditioning, synthesis_kwargs), -1.0, 1.0
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
