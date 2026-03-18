# Cross-platform justfile
set windows-shell := ["cmd.exe", "/C"]

default:
    @just --list

dev:
    just --jobs 2 dev-api dev-front

dev-api:
    python main.py

dev-front:
    python scripts/serve_docs.py --mode local --port 8080

clean:
    python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyo')]"
