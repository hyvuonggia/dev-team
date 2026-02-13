# dev-team

Minimal instructions to run the FastAPI app locally.

Prerequisites
- Python 3.13+ (project pyproject.toml requires >=3.13)
- Git (optional)

Quick start

1. (Optional) Create a virtual environment and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables:

- Copy the example file and set your OpenRouter API key:

```bash
cp .env.example .env
# Then edit .env and set OPENROUTER_API_KEY
```

The app reads `.env` via `app/config.py`.

4. Run the development server:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

5. Verify the app is running:

```bash
curl http://127.0.0.1:8000/api/v1/health
# expected: {"status":"ok"}
```

6. Call the chat endpoint (requires `OPENROUTER_API_KEY`):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}'
```

Notes / troubleshooting
- If you see a 500 from `/api/v1/chat`, ensure `OPENROUTER_API_KEY` is set in `.env`.
- If Python packages are missing, re-run `pip install -r requirements.txt` inside the active venv.
- If port 8000 is in use, change the `--port` value.
- You can call the uvicorn binary directly from the repo venv: `./.venv/bin/uvicorn app.main:app --reload`.

Files of interest
- `app/main.py` — FastAPI application and `app` object
- `app/routers/chat.py` — `/api/v1/chat` endpoint (uses OpenRouter key)
- `.env.example` — example environment variables

If you want, I can also open a PR with these changes or run the server here and show the logs.
