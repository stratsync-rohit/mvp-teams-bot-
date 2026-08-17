# Troubleshooting

| Symptom | Verify | Resolution / relevant files |
|---|---|---|
| `ModuleNotFoundError: app` in tests | Command omitted `PYTHONPATH=.` | Run `PYTHONPATH=. pytest -q`; `pytest.ini` |
| App does not start | Python/dependency version and `.env` parsing | Use Python 3.12 and reinstall `requirements.txt`; `config.py` |
| `/api/messages` returns 401/403 | App ID, secret, tenant, `APP_ENV`, incoming bearer token | Correct Entra/bot credentials; `config.py`, `main.py` |
| `/api/notifications` returns 401 | Header differs from configured key | Send matching `X-Internal-API-Key`; `routers/notifications.py` |
| Notification returns 400 | Inspect `detail` for event/schema/card type | Match schemas in `schemas/notifications.py` |
| Notification returns 502 | Find event/risk/conversation IDs in logs | Verify credentials, service URL, conversation ID, outbound network; `proactive_sender.py` |
| Card action says automation unavailable | n8n URL missing, timeout, network, or non-2xx | Check n8n workflow and `N8N_*`; `n8n_service.py` |
| Install is not visible in backend | Look for mapped-tenant `409` or registration log | Create/enable tenant mapping and verify backend/key; `backend_client.py` |
| Channel destination missing | Activity must contain channel ID and channel proof | Inspect safe diagnostic logs; `teams_context.py`, `activity_handler.py` |
| Uninstall remains active | Disconnect requires key plus team/conversation identity | Verify lifecycle event and backend response |
| Duplicate actions occur | Multiple workers/restart/window over five seconds | Use shared idempotency store; `idempotency_store.py` |
| Docker is unhealthy | No Docker `HEALTHCHECK` is defined | Probe `GET /health` from platform/container |

Logs go to stdout. Secret values and raw payloads should never be added while debugging. Since exception stack traces are usually suppressed, reproduce locally with a mocked failing dependency when logs lack detail.
