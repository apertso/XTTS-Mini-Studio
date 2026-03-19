# Cross-platform justfile
set windows-shell := ["cmd.exe", "/C"]

default:
    @just --list

dev:
    python scripts/dev.py

dev-api:
    python scripts/dev_api.py

dev-front:
    python scripts/dev_front.py

clean:
    python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyo')]"
