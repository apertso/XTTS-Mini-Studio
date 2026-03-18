#!/usr/bin/env python
from __future__ import annotations

import argparse
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parents[1]
DOCS_DIR = BASE_DIR / "docs"
CONFIG_FILE = DOCS_DIR / "config.js"
VALID_MODES = {"local", "runpod"}
API_MODE_PATTERN = re.compile(r'(apiMode\s*:\s*")([^"]+)(")')


def parse_mode(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in VALID_MODES:
        expected = ", ".join(sorted(VALID_MODES))
        raise argparse.ArgumentTypeError(f"Invalid mode {value!r}. Expected one of: {expected}")
    return normalized


def replace_api_mode(config_content: str, mode: str) -> str:
    replaced, substitutions = API_MODE_PATTERN.subn(rf"\1{mode}\3", config_content, count=1)
    if substitutions != 1:
        raise ValueError("Could not find `apiMode` field in docs/config.js")
    return replaced


class DocsHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        mode_override: str | None = None,
        config_file: Path = CONFIG_FILE,
        directory: str | None = None,
        **kwargs,
    ):
        self.mode_override = mode_override
        self.config_file = config_file
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        request_path = urlparse(self.path).path
        if request_path == "/config.js" and self.mode_override:
            self.serve_config_override()
            return
        super().do_GET()

    def serve_config_override(self):
        try:
            config_content = self.config_file.read_text(encoding="utf-8")
            overridden = replace_api_mode(config_content, self.mode_override or "")
        except Exception as exc:
            self.send_error(500, f"Failed to build in-memory config override: {exc}")
            return

        payload = overridden.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser(
        description="Serve docs/ locally with optional in-memory apiMode override for config.js"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument(
        "--mode",
        type=parse_mode,
        default=None,
        help="Optional apiMode override for config.js (local|runpod)",
    )
    args = parser.parse_args()

    handler = partial(
        DocsHandler,
        directory=str(DOCS_DIR),
        mode_override=args.mode,
        config_file=CONFIG_FILE,
    )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    mode_label = args.mode or "none"
    print(f"Serving docs from {DOCS_DIR} on http://{args.host}:{args.port} (apiMode override: {mode_label})")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping docs server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
