from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
POLL_INTERVAL_SECONDS = 0.25


def _start_process(command: List[str]) -> subprocess.Popen[bytes]:
    popen_kwargs = {"cwd": ROOT_DIR}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    return subprocess.Popen(command, **popen_kwargs)


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        process.terminate()


def _wait_for_shutdown(processes: List[Tuple[str, subprocess.Popen[bytes]]]) -> None:
    for _, process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _stop_process_tree(process)


def main() -> int:
    commands: List[Tuple[str, List[str]]] = [
        ("dev-api", [sys.executable, "scripts/dev_api.py"]),
        ("dev-front", [sys.executable, "scripts/dev_front.py"]),
    ]

    processes: List[Tuple[str, subprocess.Popen[bytes]]] = []
    try:
        for name, command in commands:
            print(f"Starting {name}: {' '.join(command)}")
            processes.append((name, _start_process(command)))

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is None:
                    continue

                message = f"{name} exited"
                if return_code != 0:
                    message += f" with code {return_code}"
                print(f"{message}. Stopping remaining processes...")

                for other_name, other_process in processes:
                    if other_name != name:
                        _stop_process_tree(other_process)

                _wait_for_shutdown(processes)
                return return_code

            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping dev processes...")
        for _, process in processes:
            _stop_process_tree(process)
        _wait_for_shutdown(processes)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
