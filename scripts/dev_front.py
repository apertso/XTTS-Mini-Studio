#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPTS_DIR.parents[0]
SERVE_DOCS_SCRIPT = SCRIPTS_DIR / "serve_docs.py"


def _exit_code_from_system_exit(exc: SystemExit) -> int:
    if isinstance(exc.code, int):
        return exc.code
    if exc.code is None:
        return 0
    print(exc.code, file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start docs dev server with local defaults."
    )
    parser.add_argument(
        "--mode",
        default="local",
        choices=("local", "runpod"),
        help="Docs API mode override (default: local).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind (default: 8080).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1).",
    )
    args = parser.parse_args()

    os.chdir(ROOT_DIR)
    argv_backup = sys.argv[:]
    sys.argv = [
        str(SERVE_DOCS_SCRIPT),
        "--mode",
        args.mode,
        "--port",
        str(args.port),
        "--host",
        args.host,
    ]
    try:
        runpy.run_path(str(SERVE_DOCS_SCRIPT), run_name="__main__")
        return 0
    except SystemExit as exc:
        return _exit_code_from_system_exit(exc)
    finally:
        sys.argv = argv_backup


if __name__ == "__main__":
    raise SystemExit(main())
