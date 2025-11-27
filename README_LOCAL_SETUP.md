# Local Setup & Regression Guide

This project targets FastAPI + openGauss. The steps below assume a fresh clone with no preinstalled dependencies.

## 1. Prepare environment variables

Copy the template and adjust values for your database:

```bash
cp .env.example .env
# Edit DATABASE_URL to point to your openGauss instance
```

Required keys are documented in `.env.example`.

## 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

## 3. Install dependencies (with a mainland mirror if needed)

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Key runtime packages include `fastapi`, `uvicorn`, `python-dotenv`, and `py-opengauss` (imported as `py_opengauss`).

## 4. Run database self-check/migrations

Ensure `DATABASE_URL` is set (env or `.env` loaded by `python-dotenv`):

```bash
python scripts/check_db.py
```

The script will print a friendly message if `py_opengauss` is missing.

## 5. Start the API server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On Windows for background runs, use `start /b` redirection as implemented in `scripts/run_backend_regression_ascii.bat`.

## 6. Run smoke tests (stdlib urllib only)

With the server running and `DATABASE_URL` configured:

```bash
PYTHONPATH=. python scripts/verify_backend_smoke.py
```

## 7. One-click regression (Windows)

A portable runner is available at `scripts/run_backend_regression_ascii.bat`. It writes logs to `.tmp/` and zips them for inspection.

## 8. Cleanup note

Temporary outputs (logs/zips under `.tmp/`) are git-ignored and safe to delete after runs.

## Mobile testing quickstart

- After the API starts, open `http://localhost:8000/` on a mobile browser. Viewport and responsive styles are enabled via `/static/mobile.css`.
- Use the floating “+” button to create a document, then open it to reach the Quill editor. Bottom toolbar and safe-area insets are tuned for touch.
- Toggle airplane mode to verify offline drafts: edit content, go back online, and observe the sync banner plus conflict prompt if the server version changed.
- Tap the bell icon to load notifications; use the filter drop-down to view unread items and tap an entry to mark it read.
