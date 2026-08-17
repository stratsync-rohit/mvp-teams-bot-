# Testing

The suite uses pytest 9.1.1, pytest-asyncio with `asyncio_mode=auto`, FastAPI `TestClient`, and `AsyncMock`/monkeypatch. `tests/conftest.py` supplies non-secret test environment defaults before app imports.

| File | Coverage focus |
|---|---|
| `test_health.py` | Health contract |
| `test_notifications.py` | Schemas, wire format, route success/errors/key |
| `test_cards.py` | Common formatting and specialized cards |
| `test_dynamic_card.py` | Dynamic sections/fallback and delivery route |
| `test_adaptive_card_invoke.py` | Invoke validation, dedupe, n8n response |
| `test_installation.py` | Context extraction and backend lifecycle calls |
| `test_proactive_sender.py` | Conversation continuation construction |

Run `PYTHONPATH=. pytest -q`. External calls and SDK sends are mocked, so these are unit/component tests rather than live integration tests. No test database exists.

## Gaps

- No real Teams tenant, JWT validation, MSAL token, n8n, or backend contract test.
- No deployment/container smoke test, concurrency test, load test, or security test.
- No coverage report or enforced threshold.
- Limited malformed-JSON/global-exception testing.
- No multi-process idempotency/state test.

At documentation time, plain `.venv/bin/pytest -q` failed import collection; the documented `PYTHONPATH=.` command is the intended validation command.
