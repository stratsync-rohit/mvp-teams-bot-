# Local development

## Prerequisites

Python 3.12 is confirmed by `Dockerfile`; a real Teams end-to-end test additionally needs a registered Microsoft app, reachable HTTPS endpoint, Teams app manifest, n8n workflow, and backend access. Their provisioning is not included here.

```bash
cd teams-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill placeholders as needed, then run:

```bash
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 3978
```

Verify `curl http://localhost:3978/health`; inspect `http://localhost:3978/docs`. With a configured internal key, test requests must send `X-Internal-API-Key`.

## Tests

```bash
PYTHONPATH=. pytest -q
```

The `PYTHONPATH=.` prefix is required in the currently observed environment; plain `.venv/bin/pytest -q` failed collection because `app` was not importable. Tests mock external Teams/n8n/backend behavior.

## Docker

```bash
docker build -t risk-teams-bot .
docker run --rm --env-file .env -p 3978:3978 risk-teams-bot
```

These commands follow the Dockerfile and `.env.example`; no Compose file exists. Avoid using production credentials in a local shared shell history.
