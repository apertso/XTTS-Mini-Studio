from __future__ import annotations

from tts.config import MODE, configure_stdio, validate_mode
from tts.core import get_runtime


def main() -> None:
    configure_stdio()
    mode = validate_mode(MODE)
    print(f"Starting XTTS backend in '{mode}' mode")

    # Pre-warm XTTS runtime once at process startup.
    get_runtime()

    if mode == "local":
        from tts.server import start_flask

        start_flask()
        return

    from tts.runpod import start_runpod

    start_runpod()


if __name__ == "__main__":
    main()

