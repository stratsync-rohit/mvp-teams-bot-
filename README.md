# Risk Teams Bot

Microsoft Teams communication layer for the Risk Notification System.

This service is **only** the Teams messaging layer:

- It receives notification payloads from n8n and renders them as Microsoft
  Teams Adaptive Cards.
- It sends those cards proactively into the correct Teams team/channel.
- It receives Adaptive Card button clicks from Teams and forwards them to
  the n8n Action Handler webhook.

It does **not** connect to MongoDB or contain risk business logic. It calls the
backend only to register a Teams installation using the Microsoft tenant ID;
n8n owns notification orchestration and the backend owns business data.

## Tech stack

- Python 3.12, FastAPI, Uvicorn
- **Microsoft 365 Agents SDK for Python** (`microsoft-agents-*` packages,
  v1.3.0) - the current Microsoft-supported Teams bot SDK. This is *not*
  the deprecated `botbuilder` / Bot Framework SDK.
- httpx (async n8n webhook calls)
- Pydantic v2 / pydantic-settings
- pytest / pytest-asyncio
- Docker

## Project structure

```
teams-bot/
├── app/
│   ├── main.py                    FastAPI app, /api/messages wiring
│   ├── config.py                  Settings + Microsoft 365 Agents SDK auth config
│   ├── bot/
│   │   ├── teams_bot.py           CloudAdapter + AgentApplication singletons
│   │   ├── activity_handler.py    conversationUpdate + Action.Execute handling
│   │   └── proactive_sender.py    Proactive send-to-channel
│   ├── cards/                     Adaptive Card renderers (one per card type)
│   ├── routers/                   health.py, notifications.py
│   ├── services/                  notification_service.py, n8n_service.py,
│   │                              conversation_service.py
│   ├── schemas/                   Pydantic models (notifications.py, actions.py)
│   ├── storage/                   conversation_store.py, idempotency_store.py
│   └── utils/logger.py
├── tests/
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD / MICROSOFT_TENANT_ID
# and N8N_ACTION_WEBHOOK_URL once available

uvicorn app.main:app --reload --host 0.0.0.0 --port 3978
```

Health check: http://localhost:3978/health

Swagger UI: http://localhost:3978/docs

OpenAPI schema: http://localhost:3978/openapi.json

## Tests

```bash
PYTHONPATH=. pytest -q
```

Tests never require a real Teams tenant or n8n instance - the Teams sender
and n8n HTTP client are mocked.

## Required `.env` values

```
APP_NAME=Risk Teams Bot
APP_ENV=development

HOST=0.0.0.0
PORT=3978

MICROSOFT_APP_ID=
MICROSOFT_APP_PASSWORD=
MICROSOFT_TENANT_ID=

N8N_ACTION_WEBHOOK_URL=
N8N_TIMEOUT_SECONDS=15

BACKEND_BASE_URL=http://localhost:8000
BACKEND_TIMEOUT_SECONDS=15

INTERNAL_API_KEY=

LOG_LEVEL=INFO
```

Notes:

- These are translated internally into the Microsoft 365 Agents SDK's
  `AgentAuthConfiguration` (see `app/config.py`) rather than requiring the
  SDK's native `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` environment
  variable naming.
- When `APP_ENV=development` **and** no `MICROSOFT_APP_ID` /
  `MICROSOFT_APP_PASSWORD` are set, `/api/messages` allows anonymous
  requests via the SDK's own documented `anonymous_allowed` mechanism -
  useful for local testing with the Bot Framework Emulator or `curl`.
  Once real credentials are configured, JWT validation is enforced.
- If `INTERNAL_API_KEY` is set, `POST /api/notifications` requires a
  matching `X-Internal-API-Key` header. If left blank, the endpoint is open
  (intended for local development only).

## Shared-bot client onboarding

Before a client installs the app, create its StratSync account and configure
its Microsoft tenant mapping in the backend:

```bash
curl -X PUT http://localhost:8000/api/teams/tenant-mappings/ACC-002 \
  -H "Content-Type: application/json" \
  -d '{"tenantId":"CLIENT_TENANT_ID","clientName":"ABC Shipping","enabled":true}'
```

The client then installs the same Teams app. The bot extracts `tenantId`,
`teamId`, `channelId`, `conversationId`, and `serviceUrl` from the Teams event
and registers them without an `accountId`. The backend resolves the account
from the tenant mapping. An unmapped tenant produces a warning and does not
interrupt Teams activity processing.

## Sample `POST /api/notifications` (initial notification)

```bash
curl -X POST http://localhost:3978/api/notifications \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: $INTERNAL_API_KEY" \
  -d '{
    "eventId": "evt-123",
    "eventType": "initial_notification",
    "riskId": "RSK-OP-0821",
    "destination": {"teamId": "TEAM_ID", "channelId": "CHANNEL_ID"},
    "notification": {
      "riskId": "RSK-OP-0821",
      "title": "Owner funding is short",
      "vessel": {"id": "V-OP-2417", "name": "MV Ocean Pioneer"},
      "severity": "high",
      "summary": "The owner needs to send US$210,000 more by 15 August 2026.",
      "deadline": "2026-08-15",
      "actions": [
        {"key": "view_details", "label": "View Details"},
        {"key": "mitigation_plan", "label": "Mitigation Plan"},
        {"key": "assign", "label": "Assign To"},
        {"key": "track_risk", "label": "Track This Problem"}
      ]
    }
  }'
```

Response:

```json
{
  "success": true,
  "eventId": "evt-123",
  "riskId": "RSK-OP-0821",
  "message": "Adaptive Card sent to Microsoft Teams"
}
```

## n8n contract

**n8n -> bot** (`POST /api/notifications`):

- `eventType: "initial_notification"` - render + send the Initial Risk Card.
- `eventType: "risk_action_result"` - render + send a follow-up card, where
  `result.cardType` is one of `risk_details`, `mitigation_plan`,
  `tracking_confirmation`, `assignment_confirmation`.

**bot -> n8n** (`POST $N8N_ACTION_WEBHOOK_URL`), sent whenever a user clicks
an Adaptive Card button in Teams:

```json
{
  "eventId": "generated-uuid",
  "riskId": "RSK-OP-0821",
  "actionKey": "view_details",
  "destination": {"teamId": "...", "channelId": "..."},
  "actor": {"id": "...", "name": "...", "aadObjectId": "..."},
  "payload": {}
}
```

Headers: `Content-Type: application/json`, `X-Correlation-ID: <eventId>`
(and `X-Internal-API-Key` if `INTERNAL_API_KEY` is configured).

## Teams / Azure configuration still required

This service is code-complete and runs locally, but going live against a
real Teams tenant requires standard Azure/Teams app registration steps that
are outside this repository:

1. **Register an Azure Bot resource / Microsoft Entra app registration**
   for the bot, and obtain `MICROSOFT_APP_ID` / `MICROSOFT_APP_PASSWORD`
   (client secret) / `MICROSOFT_TENANT_ID`.
2. **Set the messaging endpoint** on the Azure Bot resource to:

   ```
   https://YOUR-DOMAIN/api/messages
   ```

3. **Create/update the Teams app manifest** (`manifest.json`) with the bot
   ID and required scopes (`team` scope, so it can be installed into a
   Team), and package + upload/publish it to your tenant (Teams admin
   center or org app catalog).
4. **Install the Teams app into the target Team** - this triggers the
   `conversationUpdate` event this bot listens for, which captures the
   real `serviceUrl` / `conversationId` needed for proactive messaging into
   that channel (see `app/services/conversation_service.py`). Without this
   install step, `POST /api/notifications` will correctly return
   `404 Bot is not installed or channel conversation is not registered.`
5. **Grant the bot's Azure AD app the standard Bot Framework Connector
   permissions** (this is typically handled automatically by the Azure Bot
   resource registration).
6. In production, ensure `MICROSOFT_APP_ID` / `MICROSOFT_APP_PASSWORD` /
   `MICROSOFT_TENANT_ID` are set so `/api/messages` enforces real JWT
   validation (anonymous access is only ever allowed in development with no
   credentials configured).

## Docker

```bash
docker build -t risk-teams-bot .
docker run --env-file .env -p 3978:3978 risk-teams-bot
```
