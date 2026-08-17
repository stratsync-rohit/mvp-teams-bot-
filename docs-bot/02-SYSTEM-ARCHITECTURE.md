# System architecture

## Context

```mermaid
flowchart LR
  T[Microsoft Teams] -->|POST activities + JWT| M[POST /api/messages]
  M --> A[Agents SDK AgentApplication]
  A -->|installation/destination HTTP| B[StratSync backend]
  A -->|action webhook HTTP| N[n8n]
  N -->|POST notification command + optional API key| R[POST /api/notifications]
  R --> C[Card renderers]
  C --> P[CloudAdapter proactive sender]
  P -->|continued conversation| T
  H[Health monitor] -->|GET /health| F[FastAPI]
```

`app/main.py` builds FastAPI and connects its `/api/messages` route to process-wide `CloudAdapter` and `AgentApplication` instances from `app/bot/teams_bot.py`. Decorated activity handlers are registered at import time by `register_handlers()`.

## Layers

| Layer | Modules | Responsibility |
|---|---|---|
| HTTP | `main.py`, `routers/*` | Routes, header checks, transport errors |
| Bot routing | `bot/activity_handler.py` | Teams activity dispatch and event translation |
| Services | `services/*` | Notification workflow and external HTTP clients |
| Presentation | `cards/*` | Adaptive Card construction |
| Contracts | `schemas/*` | Camel-case wire validation and serialization |
| Ephemeral state | `storage/*` | Conversation references and click suppression |
| Infrastructure | `config.py`, `utils/*` | Settings, auth setup, safe logging/context extraction |

## Runtime properties

All components run in one asynchronous web process. There is no repository/database layer. `ConversationStore` and `IdempotencyStore` are in-memory singletons; their contents disappear on restart and are not shared across replicas. Proactive delivery does not currently read `ConversationStore`: n8n must supply the actual `tenantId`, `conversationId`, and `serviceUrl`.
