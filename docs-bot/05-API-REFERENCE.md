# API reference

## Endpoint summary

| Method | Path | Purpose | Authentication |
|---|---|---|---|
| GET | `/health` | Liveness response | None |
| POST | `/api/messages` | Microsoft Teams activity ingress | Agents SDK JWT; anonymous only in credential-free development |
| POST | `/api/notifications` | n8n notification command | `X-Internal-API-Key` only when configured |

FastAPI also exposes its default `/docs`, `/redoc`, and `/openapi.json`; these are not explicitly disabled or protected.

## `GET /health`

Source: `app/routers/health.py:health`. No parameters or side effects. Returns `200`:

```json
{"status":"ok","service":"teams-bot"}
```

## `POST /api/messages`

Source: `app/main.py:messages`. Called by Microsoft Teams/Bot service. The body is a Microsoft activity envelope interpreted by the Agents SDK, not a project-owned Pydantic schema. `jwt_authorization_decorator` validates the bearer token according to `AgentAuthConfiguration`; local anonymous mode is described in the authentication guide.

Activities are dispatched to handlers for `installationUpdate`, `conversationUpdate`, `message`, and `invoke`. The function returns the SDK response or an empty `200`. Exact SDK-generated authentication/error bodies are not confirmed from the current codebase.

## `POST /api/notifications`

Source: `app/routers/notifications.py:receive_notification`. Headers: optional `X-Correlation-ID`; `X-Internal-API-Key` is required and constant-time compared when `INTERNAL_API_KEY` is non-empty.

Initial notification body:

```json
{
  "eventId":"evt-123","eventType":"initial_notification","riskId":"RSK-1",
  "destination":{"tenantId":"tenant","teamId":"team","channelId":null,"conversationId":"conversation","serviceUrl":"https://smba.trafficmanager.net/apac/"},
  "notification":{"riskId":"RSK-1","title":"Funding shortfall","severity":"high","status":"open","summary":"Additional funds required.","entity":{"type":"vessel","id":"V-1","name":"MV Example","data":{}},"metrics":[]}
}
```

Action result body:

```json
{
  "eventId":"evt-124","eventType":"risk_action_result","riskId":"RSK-1","actionKey":"view_details",
  "destination":{"tenantId":"tenant","teamId":"team","conversationId":"conversation","serviceUrl":"https://smba.trafficmanager.net/apac/"},
  "result":{"success":true,"riskId":"RSK-1","actionKey":"view_details","cardType":"dynamic_card","data":{"title":"Risk details","sections":[]}}
}
```

`cardType` supports `dynamic_card`, `risk_details`, `mitigation_plan`, `tracking_confirmation`, and `assignment_confirmation`. Dynamic sections support `text`, `facts`, `bullets`, `steps`, `metrics`, `table`, and `callout`; unknown section types render a fallback. The legacy initial `vessel` envelope is normalized to `entity`.

Success is `200` with `{"success":true,"eventId":"evt-123","riskId":"RSK-1","message":"Adaptive Card sent to Microsoft Teams"}`. Errors: `400` malformed/unsupported payload, `401` bad key, `404` retained `ChannelNotRegisteredError` path (not raised by current sender), `422` may occur before handler execution for header/framework validation, and `502` normalized Teams send failure. Invalid JSON is not caught locally and follows FastAPI/Starlette behavior.
