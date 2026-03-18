from __future__ import annotations

from tts.config import (
    HF_HOME,
    HUGGINGFACE_HUB_CACHE,
    MODE,
    MODEL_DIR,
    MODEL_ID,
    configure_stdio,
    validate_mode,
)
from tts.core import get_runtime


def _format_path(path) -> str:
    return str(path) if path is not None else "<unset>"


def main() -> None:
    configure_stdio()
    mode = validate_mode(MODE)
    print(f"Starting XTTS backend in '{mode}' mode")
    print(
        "Model env startup: "
        f"MODEL_ID={MODEL_ID}, "
        f"MODEL_DIR={_format_path(MODEL_DIR)}, "
        f"HF_HOME={_format_path(HF_HOME)}, "
        f"HUGGINGFACE_HUB_CACHE={_format_path(HUGGINGFACE_HUB_CACHE)}"
    )

    if mode == "local":
        # Keep local API behavior unchanged: load once at startup.
        get_runtime()
        from tts.server import start_flask

        start_flask()
        return

    print("RunPod mode: XTTS runtime will load lazily on first request.")
    from tts.runpod import start_runpod

    start_runpod()


if __name__ == "__main__":
    main()
