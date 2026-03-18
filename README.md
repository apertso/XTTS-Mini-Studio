# XTTS Mini Studio

[Open Prod](https://apertso.github.io/XTTS-Mini-Studio/)

![XTTS Mini Studio](docs/preview.png)

## Quick Start (via `just`)

### 1) Install backend dependencies

```bash
python -m pip install -r requirements.api.txt
```

### 2) Start locally (fastest)

```bash
just dev
```

Then open `http://127.0.0.1:8080`.

## Run API with Docker

Docker Hub image: <https://hub.docker.com/r/apertso/xtts-runpod>

```bash
docker pull apertso/xtts-runpod:latest
docker run --rm -p 5000:5000 -e TTS_MODE=local -e TTS_HOST=0.0.0.0 -e TTS_PORT=5000 apertso/xtts-runpod:latest
```

Health check:

```bash
curl http://127.0.0.1:5000/health
```

## XTTS Precision Override (optional)

Set `XTTS_PRECISION` to one of: `auto` (default), `fp32`, `fp16`.

- `auto`: `local -> fp32`, `runpod + CUDA -> fp16 autocast`
- `fp32`: force fp32
- `fp16`: request fp16 autocast (falls back to fp32 on runtime error)

Set `XTTS_PRECISION` in your current shell/session before running `python main.py`.
