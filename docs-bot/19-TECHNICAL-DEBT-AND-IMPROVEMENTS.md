# Technical debt and improvements

These are observed recommendations; none were implemented during documentation work.

## Critical

| Problem | Evidence | Impact | Improvement |
|---|---|---|---|
| Production can run with open internal notification ingress | `_verify_internal_api_key` allows blank key regardless of `APP_ENV` | Unauthorized Teams messages | Fail production startup and requests without a key |

## High

| Problem | Evidence | Impact | Improvement |
|---|---|---|---|
| Caller-controlled Teams `serviceUrl` | `Destination` accepts any string; sender uses it | Trust-boundary/SSRF risk | Validate against Microsoft service URL policy |
| Replica-local volatile deduplication | `IdempotencyStore` singleton | Duplicate n8n actions | Redis `SET NX` with TTL and stable event identity |
| Conversation store is volatile and unused for sending | `InMemoryConversationStore`; sender uses request destination | Lost/stale context, dead abstraction | Persist or remove/clarify ownership |
| No retry/durable delivery | All outbound clients make one request | Transient event/notification loss | Bounded retry plus durable queue/idempotency |

## Medium

| Problem | Evidence | Impact | Improvement |
|---|---|---|---|
| Diagnostic fields silently dropped | logger allowlist lacks `error_type`, `card_type`, flags | Hard incident diagnosis | Expand safe schema and add exception context safely |
| New HTTP client per call | backend/n8n service methods | Connection overhead | Lifespan-managed shared clients |
| No uniform exception envelope | Route-local mappings only | Inconsistent clients/debugging | Typed global handlers with correlation IDs |
| `HOST`/`PORT` settings unused by app/container command | `Settings` vs hard-coded Docker CMD | Configuration surprise | Remove or wire through startup wrapper |
| Default API docs exposed | FastAPI defaults | Information disclosure | Disable/protect in production |
| No live contract/security/load tests | test suite is mocked | Integration regressions | Staging E2E and automated negative tests |

## Low

| Problem | Evidence | Impact | Improvement |
|---|---|---|---|
| `ChannelNotRegisteredError` retained but current sender never raises it | `proactive_sender.py` | Misleading 404 path | Remove after compatibility review |
| Comments conflict with behavior | n8n service says bot never talks to backend | Handover confusion | Update module description |
| Specialized legacy cards overlap dynamic cards | `_CARD_BUILDERS` | Maintenance surface | Define deprecation/migration plan |
| No Docker healthcheck or deployment metadata | Dockerfile only | Weaker operability | Add platform health probe and deployment runbook |

No TODO/FIXME markers, database indexes, or migrations were found because the service has no database layer.
