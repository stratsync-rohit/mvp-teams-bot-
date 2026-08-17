# Developer handover

## Start here

Understand the ownership boundary first: this process translates and transports Teams/n8n/backend messages; it owns no risk business state. Read `main.py`, `bot/activity_handler.py`, `services/notification_service.py`, both schema files, and `config.py`, then run the tests.

Critical endpoints are `/api/messages` and `/api/notifications`. Critical external access is the Microsoft app/tenant, n8n action workflow, and backend lifecycle API. There are no local database collections.

## Common changes

### Add a notification/card type

Define or intentionally keep the result data contract, add a builder under `app/cards`, register it in `_CARD_BUILDERS`, add route/schema/render tests, and coordinate the exact `cardType` with n8n. Prefer `dynamic_card` sections for presentation variants that do not need bespoke behavior.

### Add a Teams activity

Register a decorator in `register_handlers`, keep parsing through `extract_teams_context`, decide whether failure must be synchronous or best-effort, and test with a fake turn context. Do not bypass SDK authentication.

### Change n8n/backend contracts

Update Pydantic aliases or backend payload construction, client behavior, tests, sample docs, and the external workflow/service together. The bot intentionally never supplies backend `accountId`.

### Add persistence

Implement the `ConversationStore` protocol or a shared atomic idempotency interface, configure it explicitly, add lifecycle/expiry tests, and document operational dependencies. Do not introduce risk-data access here without revisiting the service boundary.

### Add an API

Create a router, Pydantic request/response models, explicit authentication, service-level behavior, error mapping, and tests; include the router in `main.py`.

## High-impact areas

Changes to auth configuration, Teams `ConversationReference`, wire aliases, lifecycle context extraction, card action data, or error swallowing affect cross-system compatibility. Test these with both component tests and a real non-production Teams installation before deployment.

## Operating checklist

Use Python 3.12, configure all production credentials, run `PYTHONPATH=. pytest -q`, build the container, smoke-test `/health`, then validate install, proactive notification, button action, follow-up notification, and uninstall. The actual deployment/rollback platform is not confirmed from this repository.
