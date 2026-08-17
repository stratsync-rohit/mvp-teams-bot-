# Configuration and environment

`Settings` in `app/config.py` uses pydantic-settings with `.env`, UTF-8, case-insensitive names, and ignored extra keys. Process environment values take precedence over dotenv values. `get_settings()` is cached, so tests or runtime changes require cache clearing/restart.

| Variable | Required | Purpose | Safe example |
|---|---:|---|---|
| `APP_NAME` | No | FastAPI title/log name | `Risk Teams Bot` |
| `APP_ENV` | No | Controls anonymous local Teams mode | `production` |
| `HOST` | No | Documented bind host; read but not wired to Uvicorn | `0.0.0.0` |
| `PORT` | No | Documented port; read but not wired to Uvicorn | `3978` |
| `MICROSOFT_APP_ID` | Production | Bot/client identity | `<microsoft-app-id>` |
| `MICROSOFT_APP_PASSWORD` | Production | Client secret | `<secret>` |
| `MICROSOFT_TENANT_ID` | Production | Entra tenant | `<tenant-id>` |
| `N8N_ACTION_WEBHOOK_URL` | Action flow | Outbound action endpoint | `https://n8n.example/webhook/<id>` |
| `N8N_TIMEOUT_SECONDS` | No | n8n timeout | `15` |
| `BACKEND_BASE_URL` | Lifecycle flow | Backend origin | `https://backend.example` |
| `BACKEND_TIMEOUT_SECONDS` | No | Backend timeout | `15` |
| `INTERNAL_API_KEY` | Production | Internal ingress/outbound shared key | `<secret>` |
| `LOG_LEVEL` | No | Python root level | `INFO` |

`.env.example`, source settings, and README list the same variables. Docker does not copy `.env`; inject values at runtime. No Compose/CI configuration is present. Do not place real secrets in documentation, logs, images, or source control.

Observed inconsistency: `HOST` and `PORT` do not affect the hard-coded Docker `CMD`; local CLI commands must supply them separately.
