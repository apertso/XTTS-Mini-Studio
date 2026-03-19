# XTTS Mini Studio

Live Demo - https://apertso.github.io/XTTS-Mini-Studio/

![XTTS Mini Studio](docs/preview.png)

## What Is Where

- Backend API: `tts/` (entrypoint: `python -m tts`)
- Frontend app: static files in `docs/`

## Quick Start

### 1) Install backend dependencies

```bash
python -m pip install -r requirements.api.txt
```

### 2) Start API + frontend together

```bash
just dev
```

This starts:

- API at `http://127.0.0.1:5000`
- Frontend at `http://127.0.0.1:8080`
