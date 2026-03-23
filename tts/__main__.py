from __future__ import annotations

from .config import (
    HF_HOME,
    HUGGINGFACE_HUB_CACHE,
    MODE,
    MODEL_ID,
    TTS_DEVICE_SETTING,
    configure_stdio,
    validate_mode,
)
from .core import get_runtime


def _format_path(path) -> str:
    return str(path) if path is not None else "<unset>"


def main() -> None:
    configure_stdio()
    mode = validate_mode(MODE)
    print(f"Starting Kokoro backend in '{mode}' mode")
    print(
        "Model env startup: "
        f"MODEL_ID={MODEL_ID}, "
        f"TTS_DEVICE={TTS_DEVICE_SETTING}, "
        f"HF_HOME={_format_path(HF_HOME)}, "
        f"HUGGINGFACE_HUB_CACHE={_format_path(HUGGINGFACE_HUB_CACHE)}"
    )

    if mode == "local":
        # Keep local API behavior unchanged: load once at startup.
        get_runtime()
        from .server import start_flask

        start_flask()
        return

    print("RunPod mode: Kokoro runtime will load lazily on first request.")
    from .runpod import start_runpod

    start_runpod()


if __name__ == "__main__":
    main()
