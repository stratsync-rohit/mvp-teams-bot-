# Codebase structure

```text
teams-bot/
├── app/
│   ├── main.py                 FastAPI entry point
│   ├── config.py               Settings and Agents SDK authentication
│   ├── bot/                    SDK singletons, handlers, proactive send
│   ├── cards/                  Adaptive Card renderers/helpers
│   ├── routers/                Health and internal notification routes
│   ├── schemas/                Incoming/outgoing Pydantic contracts
│   ├── services/               Workflow and outbound HTTP clients
│   ├── storage/                In-memory stores
│   └── utils/                  Logging and Teams context extraction
├── tests/                      pytest suite
├── docs/                       Developer handover documentation
├── .env.example               Configuration template
├── Dockerfile                 Python 3.12 image
├── requirements.txt           Exact Python dependencies
└── pytest.ini                 asyncio test mode
```

## Architecturally important files

| File | Responsibility; important symbols | Used by / dependencies |
|---|---|---|
| `app/main.py` | App construction, `lifespan`, `messages` | Uvicorn; routers and Agents SDK |
| `app/config.py` | `Settings`, cached settings, auth and MSAL factories | All integrations and startup |
| `app/bot/teams_bot.py` | Process-wide `adapter`, `agent_app`, auth config | Main route, handlers, proactive sender |
| `app/bot/activity_handler.py` | `register_handlers`, lifecycle handlers, `handle_invoke` | AgentApplication; backend/n8n services |
| `app/bot/proactive_sender.py` | `send_to_conversation` constructs a continuation reference | Notification service; CloudAdapter |
| `app/routers/notifications.py` | Key check, event discriminator, HTTP error mapping | Notification service and schemas |
| `app/services/notification_service.py` | Render dispatch and Teams send normalization | Card builders and proactive sender |
| `app/services/backend_client.py` | Installation/destination/disconnect HTTP calls | Activity handler; httpx |
| `app/services/n8n_service.py` | Action webhook call and failure normalization | Invoke handler; httpx |
| `app/services/conversation_service.py` | Captures conversation reference in memory | Lifecycle handlers and store |
| `app/schemas/notifications.py` | n8n-to-bot payloads and response | Router/service |
| `app/schemas/actions.py` | bot-to-n8n event | Invoke handler/n8n service |
| `app/cards/dynamic_card.py` | Extensible section renderer | Notification service |
| `app/storage/*` | Store protocol/implementation and idempotency singleton | Conversation service/invoke handler |

`__init__.py` files contain no behavior. The card modules are intentionally isolated by output type; common primitives live in `cards/common.py`.
