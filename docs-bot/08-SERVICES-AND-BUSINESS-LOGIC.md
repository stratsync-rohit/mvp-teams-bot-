# Services and business logic

The repository implements transport and rendering rules, not risk-domain logic.

## `NotificationService`

Location: `app/services/notification_service.py`. Inputs are validated notification payloads; output is `NotificationResponse`. It selects an initial or action-result renderer, passes destination context to `send_to_conversation`, logs the resulting message ID, and normalizes unexpected send errors to `TeamsSendError`. Unsupported card types become `UnsupportedCardTypeError`.

## `N8nService`

Location: `app/services/n8n_service.py`. `send_action_event` serializes `RiskActionEvent` with camel-case aliases and posts it with correlation and optional internal-key headers. Missing URL, timeout, network error, and non-2xx status all raise `N8nActionWebhookError`. It performs one attempt and returns no response payload.

## Backend client

Location: `app/services/backend_client.py`.

- `register_teams_installation` posts `/api/teams/installations`; `409` is treated as an unmapped tenant and returns false.
- `register_teams_destination` posts `/api/teams/channel-destinations`.
- `disconnect_teams_installation` posts `/api/teams/installations/disconnect`, requires the internal key, and returns `disconnected`, `not_found`, or `failed`.

Each call creates a new `httpx.AsyncClient`. Registration failures are logged and converted to false; lifecycle handling deliberately continues.

## `ConversationService`

Location: `app/services/conversation_service.py`. It extracts Teams context and stores only channel references having team, channel, conversation, and service URL. `tenant_id` can be stored as an empty string, although upstream lifecycle registration requires it. The abstraction anticipates a persistent implementation but currently uses memory.

## Presentation rules

`notification_service._CARD_BUILDERS` dispatches action results. `initial_risk_card.py` emits only View Details and Mitigation Plan actions carrying `riskId` plus `actionKey`. `dynamic_card.py` preserves section order and safely renders unknown section data. Legacy specialized renderers remain supported.
