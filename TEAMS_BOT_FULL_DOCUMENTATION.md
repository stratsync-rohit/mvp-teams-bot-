# Teams Bot Full Documentation

Documentation snapshot: 2026-08-24. Source of truth: the current teams-bot working tree and tests, plus the narrowly related backend Compose/Teams files named in §33. No secret values were read into or reproduced in this document.

# 1. Executive Summary

The Teams bot is StratSync's Microsoft Teams transport and presentation service. It accepts notification instructions from n8n, renders Adaptive Cards, posts them to an existing Teams conversation, receives Teams lifecycle activities and card actions, persists Teams installation/discovery state through the StratSync backend, and forwards user actions to n8n.

It does not own risks, account mappings, notification orchestration, or MongoDB data. Those belong to the backend and n8n. The frontend/backend owns the explicit UI Connect operation; the bot supplies Microsoft conversation resolution and delivery.

The current runtime is Bot Framework-channel-only in the architectural sense: Teams activities arrive through the Bot Framework protocol and outbound messages use the Bot Framework connector. The implementation library is Microsoft 365 Agents SDK 1.3.0, not the deprecated Python botbuilder package. Microsoft Graph is absent from the current working tree.

Main responsibilities:

- Expose POST /api/messages for authenticated Teams activities.
- Register Team installation metadata with the backend.
- Discover channels from authoritative Teams activity context.
- Keep every Teams lifecycle path discovery-only; register a destination only after explicit StratSync UI Connect.
- Resolve an explicit channel connection through Microsoft create_conversation.
- Render Adaptive Card 1.5 payloads and send them proactively.
- Forward Action.Execute clicks to n8n with actor and destination context.
- Soft-disconnect Team/channel state through the backend.

External dependencies are Microsoft Teams/Bot Framework Connector and Entra token services, the StratSync backend, n8n, and runtime JWKS endpoints used by the Agents SDK. The service has no database, queue, scheduler, or worker.

Important limitations include no durable retry after a failed installation enumeration, caller-supplied proactive routes, volatile process-local stores, no retries/durable delivery, permissive internal authentication in development, no live Teams/JWT/MSAL integration tests, and no DNS-resolving service-URL allowlist.

# 2. Repository Structure

Build artifacts, caches, .venv, .pytest_cache, __pycache__, .DS_Store, and .git internals are excluded.

| Path | Purpose, major symbols, and runtime role |
|---|---|
| app/main.py | Entrypoint. Configures logging, calls register_handlers, creates FastAPI, includes routers, exposes messages, and defines lifespan. |
| app/config.py | Settings, get_settings, get_agent_auth_configuration, get_connection_manager. Translates simple environment names into Agents SDK authentication/MSAL configuration. |
| app/bot/teams_bot.py | Creates process-wide connection_manager, CloudAdapter adapter, AgentApplication agent_app with MemoryStorage, and inbound agent_auth_configuration. |
| app/bot/activity_handler.py | Thin SDK activity registration, lifecycle branching, disconnect-command response, and invoke response sending. |
| app/bot/proactive_sender.py | send_to_conversation builds a ConversationReference and uses adapter.continue_conversation to send a card. |
| app/routers/health.py | GET /health. |
| app/routers/notifications.py | Notification discrimination/validation, POST /api/notifications, and transport error mapping. |
| app/routers/channel_resolution.py | POST /api/internal/teams/resolve-channel-conversation. |
| app/schemas/actions.py | ActionDestination, ActionActor, RiskActionEvent and camel-case n8n serialization. |
| app/schemas/notifications.py | Destination and notification/action-result request/response models; legacy vessel normalization. |
| app/schemas/teams.py | Validated internal channel-resolution request contract. |
| app/services/adaptive_card_actions.py | Invoke validation, deduplication, action DTO construction, n8n forwarding, and InvokeResponse construction. |
| app/services/backend_client.py | Bot-to-backend HTTP calls, controlled results, and the lifespan-owned shared client. |
| app/services/conversation_service.py | Capture/save/get channel references and resolve_channel_conversation through the Microsoft connector. |
| app/services/n8n_service.py | N8nService.send_action_event and N8nActionWebhookError. |
| app/services/notification_service.py | Card dispatch, proactive send orchestration, Teams error classification, and response construction. |
| app/services/teams_channel_discovery.py | Existing-channel enumeration and failure-isolated discovery persistence. |
| app/services/teams_lifecycle.py | Installation/discovery/disconnect persistence orchestration independent of SDK routing. |
| app/storage/conversation_store.py | ChannelConversationReference protocol and process-local InMemoryConversationStore singleton. |
| app/storage/idempotency_store.py | Thread-locked, process-local five-second duplicate-action cache. |
| app/utils/teams_context.py | Dict/SDK-safe Teams context, channel proof, explicit install selection, and diagnostics. |
| app/utils/internal_auth.py | Constant-time internal API-key verification shared by internal routers. |
| app/utils/service_url.py | Central HTTPS connector serviceUrl validation. |
| app/utils/logger.py | stdout logging configuration and safe-field allowlisted log_event. |
| app/cards/common.py | Adaptive Card 1.5 primitives, formatting, Action.Execute buttons, and attachment wrapping. |
| app/cards/initial_risk_card.py | Generic initial risk/entity/metrics card. |
| app/cards/dynamic_card.py | Ordered text, facts, bullets, steps, metrics, table, callout, and safe unknown-section rendering. |
| app/cards/risk_details_card.py | Legacy/specialized risk-details follow-up card. |
| app/cards/mitigation_plan_card.py | Legacy/specialized mitigation-plan follow-up card. |
| app/cards/tracking_card.py | Tracking confirmation card. |
| app/cards/assignment_card.py | Assignment confirmation and currently unused simple text-input fallback. |
| app/**/__init__.py | Package markers; no runtime logic. |
| tests/conftest.py | Sets credential-free deterministic test environment before imports. |
| tests/test_health.py | Health contract. |
| tests/test_installation.py | Teams context, lifecycle, discovery, fake-channel, registration, disconnect, and message behavior. |
| tests/test_adaptive_card_invoke.py | Invoke success and duplicate-action JSON response behavior. |
| tests/test_notifications.py | Schemas, n8n client, notification route, internal key, and error normalization. |
| tests/test_proactive_sender.py | Continuation and Microsoft create_conversation route IDs. |
| tests/test_cards.py | Common formatting and specialized card behavior. |
| tests/test_dynamic_card.py | Dynamic rendering, unknown sections, and notification compatibility. |
| requirements.txt | Fully pinned direct Python dependencies. |
| pytest.ini | pytest-asyncio auto mode. |
| Dockerfile | Python 3.12 non-root runtime image and fixed Uvicorn command. |
| .env.example | Complete application environment template. |
| .gitignore | Excludes secrets, environments, caches, logs, and builds. |
| README.md | Operator/developer overview; some statements should be checked against this document and current code. |
| docs-bot/*.md | Existing split handover documents. They are informational; current code/tests remain authoritative. |

# 3. Technology Stack

| Technology | Version/evidence | Use |
|---|---|---|
| Python | 3.12-slim in Dockerfile | Production interpreter. The local .venv used for verification was Python 3.14, which is not the container target. |
| FastAPI | 0.141.1 | HTTP app, routing, validation integration, OpenAPI/docs. |
| Uvicorn standard | 0.52.1 | ASGI server. |
| Microsoft 365 Agents SDK | microsoft-agents activity/core/fastapi/teams/authentication-msal 1.3.0 | Bot Framework activities, JWT validation, dispatch, Connector calls, proactive continuation, MSAL. |
| httpx | 0.28.1 | Async backend and n8n calls. |
| Pydantic | 2.13.4 | Wire models. |
| pydantic-settings | 2.15.0 | Environment/.env loading. |
| python-dotenv | 1.2.2 | Environment-loading dependency. |
| Adaptive Cards | Schema 1.5 | Teams cards. |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | Unit/component tests. |
| Docker | python:3.12-slim | Container build; curl installed for manual probes. |
| Logging | Python logging | Timestamped stdout logs plus allowlisted structured suffixes. |

# 4. Application Startup

Startup sequence:

1. Uvicorn imports app.main:app.
2. app/config.py get_settings reads process environment and .env once; lru_cache holds the result.
3. Importing app.bot.teams_bot calls get_connection_manager. It creates MsalConnectionManager with SERVICE_CONNECTION, then CloudAdapter, AgentApplication with bot_app_id and SDK MemoryStorage, and AgentAuthConfiguration.
4. app/main.py calls configure_logging(settings.LOG_LEVEL).
5. register_handlers registers four AgentApplication routes: installation_update, conversation_update, message, and invoke.
6. FastAPI is created with title, version 1.0.0, and lifespan.
7. app.state.agent_configuration receives the auth configuration used by jwt_authorization_decorator.
8. health, notifications, and channel_resolution routers are included.
9. POST /api/messages is declared.
10. Lifespan logs startup, yields, and logs shutdown. No clients are opened/closed and no background jobs run in lifespan.

The Docker command is uvicorn app.main:app --host 0.0.0.0 --port 3978. Settings HOST and PORT are read but do not alter this hard-coded command. FastAPI also exposes default /docs, /redoc, /openapi.json, and /docs/oauth2-redirect.

POST /api/messages reads JSON, emits only allowlisted activity-envelope metadata through the safe structured logger, then calls start_agent_process(request, agent_app, adapter). Message text, card payloads, headers, tokens, and the complete raw body are not logged. A null SDK response becomes HTTP 200.

# 5. Environment Variables

Settings are case-insensitive, extra names are ignored, .env is UTF-8, and process environment overrides dotenv. Empty strings are defaults where shown.

| Variable | Required | Default | Used in | Purpose / missing behavior | Sensitive |
|---|---|---|---|---|---|
| APP_NAME | No | Risk Teams Bot | config.py, main.py | App title/startup logs. | No |
| APP_ENV | Production behavior requires correct value | development | config.py | development/dev/local enables anonymous Teams ingress only when both app ID and password are absent. | No |
| HOST | No | 0.0.0.0 | Settings only | Documentary/config value; current Docker command ignores it. | No |
| PORT | No | 3978 | Settings only | Documentary/config value; current Docker command ignores it. | No |
| MICROSOFT_APP_ID | Required for real Teams | empty | config.py, teams_bot.py, conversation_service.py, proactive_sender.py | JWT audience, bot identity, connector operations. Missing with password in development permits anonymous ingress; outbound Microsoft calls cannot authenticate reliably. | Identifier, not secret |
| MICROSOFT_APP_PASSWORD | Required for real Teams | empty | config.py/MSAL | Client secret for outbound token acquisition. Missing prevents usable client-secret auth. | Yes |
| MICROSOFT_TENANT_ID | Required for configured tenant auth | empty | config.py/MSAL/JWT key selection | Entra authority/keys and tenant context. Missing makes production auth unusable/unclear from current code. | Identifier |
| N8N_ACTION_WEBHOOK_URL | Required for card actions | empty | n8n_service.py | Target for Action.Execute events. Missing logs warning, raises controlled error, and user gets automation-unavailable response. | Treat as sensitive endpoint |
| N8N_TIMEOUT_SECONDS | No | 15 | n8n_service.py | httpx timeout seconds. | No |
| BACKEND_BASE_URL | Required for lifecycle/discovery | http://localhost:8000 | backend_client.py | Base for four backend endpoints. Missing cannot occur under model default; unreachable calls fail safely. | Usually no |
| BACKEND_TIMEOUT_SECONDS | No | 15 | backend_client.py | Timeout for backend HTTP calls. | No |
| INTERNAL_API_KEY | Required when APP_ENV=production; optional for local development | empty | notification/channel-resolution routes, backend/n8n clients | Matching X-Internal-API-Key in production. Startup fails closed in production when blank. | Yes |
| LOG_LEVEL | No | INFO | main.py/logger.py | Root logging level; invalid names fall back to INFO. | No |

No additional environment reads exist in application code. The SDK-native CONNECTIONS__... names appear only in explanatory comments and are not consumed by this service configuration.

# 6. Authentication

## Bot Framework inbound authentication

Only POST /api/messages uses jwt_authorization_decorator. It reads Authorization, requires Bearer token format unless anonymous mode is enabled, validates the RS256 signature using Bot Framework keys for issuer https://api.botframework.com or configured-tenant Entra keys otherwise, applies standard JWT time checks with five-minute leeway, and manually requires aud to equal a configured CLIENT_ID. Valid claims are placed in request.state.claims_identity.

The current pinned SDK's validator chooses keys using token issuer but does not receive a separate issuer allowlist argument in the repository integration. The repository itself performs no post-JWT issuer, tenant-claim, or activity channelData.tenant.id comparison.

Anonymous access is true only when APP_ENV is development/dev/local and both app ID and password are blank. If either credential is partially configured, anonymous access is false.

Invalid audience means the JWT aud claim is not the configured MICROSOFT_APP_ID. Typical causes are a token issued for a different bot/app registration, mismatched environment/Teams manifest/Azure Bot IDs, or blank/wrong app ID.

HTTP 401 is returned for a missing Authorization header outside anonymous mode, malformed Bearer syntax, signature/key/JWT failures, expiry/not-before errors, or invalid audience. The SDK returns a generic Invalid token or authentication failed body after validation errors. Missing app auth configuration would be 500, but main.py always assigns it.

MICROSOFT_TENANT_ID configures Entra authority/key lookup and outbound credential authority. Activity tenantId is used in business routing, but no explicit application-level equality check against MICROSOFT_TENANT_ID exists.

## Outbound proactive authentication

get_connection_manager creates an MSAL client-secret provider from app ID, password, and tenant. continue_conversation/create_conversation creates connector credentials; the SDK asks MSAL for a client-credential token for the connector audience/scope and sends it as Bearer authentication to the supplied serviceUrl. Explicit resolution passes audience https://api.botframework.com/.default. Normal continuation derives the token audience/scope from SDK claims identity.

## Bot Framework versus Microsoft Graph

Bot Framework/Connector authentication is required for real inbound and outbound Teams operation. Microsoft Graph authentication is not implemented or required. There are no Graph tokens, Graph endpoints, delegated permissions, or Graph client calls in the current working tree.

# 7. HTTP API Routes

| Method/path | Source / handler | Request | Response | Authentication / key | Side effects and errors |
|---|---|---|---|---|---|
| GET /health | app/routers/health.py health | None | 200: status ok, service teams-bot is running | None | No dependency checks. |
| POST /api/messages | app/main.py messages | Bot Framework Activity JSON | SDK response or 200 | Agents SDK Bearer JWT; anonymous only under narrow development condition. No internal key. | Dispatches lifecycle/message/invoke; may call backend/n8n or send Teams replies. Invalid JSON is framework error; unhandled SDK/handler failures are not locally normalized. |
| POST /api/notifications | app/routers/notifications.py receive_notification | InitialNotificationPayload or ActionResultPayload selected by eventType | NotificationResponse | X-Internal-API-Key only if INTERNAL_API_KEY is nonempty | Renders/sends a card. 400 malformed/unsupported; 404 legacy ChannelNotRegisteredError; 410 permanent Teams destination failure; 503 retryable failure; 401 wrong/missing configured key. |
| POST /api/internal/teams/resolve-channel-conversation | app/routers/channel_resolution.py resolve_channel_conversation | tenantId, teamId, channelId, serviceUrl: nonempty strings | conversationId | Same optional X-Internal-API-Key | Calls Microsoft create_conversation and posts a readiness text activity. Validation is normally 422. Microsoft/runtime exceptions are unhandled and normally become 500. |
| GET/HEAD /openapi.json, /docs, /redoc, /docs/oauth2-redirect | FastAPI defaults | N/A | Documentation UI/schema | None | Exposes API contract. |

# 8. Microsoft Teams Activity Handling

register_handlers installs exactly four top-level activity handlers.

| Activity/event | Exact dispatch | Fields and validation | Effects / skips |
|---|---|---|---|
| installationUpdate/add | on_installation_update → handle_installation_update | action; extracted tenant/team/conversation/service; diagnostic metadata; optional explicit selectedChannel | Registers Team installation, enumerates existing channels through TeamsInfo, and records a valid selected channel as discovery only. Never resolves or registers a destination. |
| installationUpdate/remove | same | tenant plus teamId or conversationId | Backend Team-scoped disconnect. Incidental channel fields never narrow uninstall to a channel. Failures are swallowed. |
| conversationUpdate channelCreated | on_conversation_update → handle_conversation_update | eventType, tenant/team/channel/name/service; explicit event is trusted even if conversation is Team-scoped | Records available discovery and returns. Never creates/resolves destination. |
| conversationUpdate channelDeleted/channelRemoved | same | same required discovery fields | Marks discovery unavailable and returns. Does not directly disconnect a destination in bot code. |
| conversationUpdate channelMemberAdded | same → handle_channel_member_added | type must be conversationUpdate; eventType exact after lowercasing; membersAdded must contain recipient.id; authoritative channel conversation requires conversationType channel and conversation.id == channelId | Refreshes Team installation and records discovery only. It never creates, reconnects, or saves a destination route. |
| conversationUpdate teamMemberAdded | generic conversation-update path | No special top-level handler | May record authoritative discovery and refresh installation; never registers destination through member-added path. |
| generic conversationUpdate | same | Authoritative channel proof for discovery; basic Team identity for installation | Discovery-only plus installation refresh. No destination registration. |
| message | on_message → handle_message | Any authoritative channel activity may be discovery; mention-tolerant exact disconnect command | Records discovery. Only disconnect is a command. connect and ordinary messages have no reply and never create/reconnect destinations. |
| invoke named adaptiveCard/action | on_invoke → handle_invoke | value.action.data must contain riskId and actionKey; destination/actor extracted; five-second key activity.id:riskId:actionKey | Forwards event to n8n and returns embedded AdaptiveCardInvokeResponse 200 or 502. Duplicate returns already-processing. Missing identifiers returns embedded 400. |
| other invoke | handle_invoke | activity.name differs | Sends InvokeResponse status 200 with no application action. |
| installationUpdate other action | handle_installation_update | action neither add nor remove | No action. |
| member removal, teamDeleted, installation event subtypes not named above | No dedicated route/branch | Only generic conversation-update behavior if delivered as conversationUpdate | No proven special semantics; teamDeleted is not explicitly handled. |

There are no handlers for messageReaction, typing, event, endOfConversation, meeting activities, sign-in invoke, task/fetch, or member-removed-specific logic.

# 9. Bot Framework Channel Discovery

Discovery means persisting an observed channel in backend available-channel state. It does not inherently create a notification destination.

Sources:

- installationUpdate/add enumeration through `TeamsInfo.get_team_channels(context, team_id)`, including channels that predate installation.
- channelCreated: explicit-event discovery, even when its conversation ID is Team-scoped.
- A genuine generic conversationUpdate: requires has_authoritative_channel_conversation.
- installationUpdate/add with explicit selectedChannel: records discovery only.
- channelMemberAdded: the verified bot-added path refreshes installation metadata and records discovery only.
- Any message with genuine channel context: discovery runs before command parsing.

extract_teams_context produces tenantId, teamId, teamName, channelId, channelName, conversationId, serviceUrl, aadGroupId, actor metadata, and channelResolutionSource. Canonical Team ID is channelData.team.id, falling back to teamsTeamId. Channel candidates are named channelData.channel.id, teamsChannelId, settings.selectedChannel.id, then selectedChannel.id.

Fake-channel protection:

- An unnamed channelData.channel.id equal to teamId is rejected as ambiguous.
- An equal ID is accepted when channelData.channel carries an explicit name, supporting General.
- Selected channels equal to teamId are rejected unless the name is General.
- A Team-level selectedChannel shape without a real name is rejected.
- Discovery requires a nonempty channel name.
- Generic discovery requires conversationType channel, conversationId == channelId, and tenant/team/channel/service.
- Personal, groupChat, and meeting contexts are not authoritative.
- Missing/malformed fields produce no operation, not fabricated IDs.
- Backend discovery uses an upsert identity accountId + tenantId + teamId + channelId, making duplicates idempotent.

aadGroupId is retained only as optional discovery metadata. It never replaces Bot Framework teamId.

# 10. Team Installation Lifecycle

Team install → POST /api/messages → Agents SDK installation_update dispatch → handle_installation_update(add) → register_installation_from_activity → extract_teams_context → register_teams_installation → POST backend /api/teams/installations.

The registration payload includes all extracted fields plus botAppId and enabled true; no accountId is supplied. The backend maps tenantId to an account. Required locally are tenantId, teamId, conversationId, and serviceUrl. teamName/channel/actor/aadGroupId are optional.

Repeated events are sent again; backend behavior is an idempotent upsert. A backend 409 means unmapped tenant, is logged, and does not fail Teams processing. Other HTTP/JSON failures return false.

After installation persistence, installationUpdate/add enumerates existing Team channels using the Agents SDK connector API. It then examines explicit channel selection; a valid selection is also persisted as discovery state. Both paths remain discovery-only.

installationUpdate/remove → disconnect_installation_from_activity → POST /api/teams/installations/disconnect with scope team and tenantId plus teamId and/or conversationId. Backend not_found counts as handled. INTERNAL_API_KEY must be configured for the bot to make this disconnect call. An uninstall disables Team-owned destinations in backend behavior; an uninstall missed before this code existed cannot be replayed automatically.

teamMemberAdded is not treated as installation add. channelMemberAdded refreshes installation metadata before authoritative discovery validation.

# 11. Channel Discovery Lifecycle

Teams channel activity
→ POST /api/messages in app/main.py
→ Agents SDK handler from register_handlers
→ handle_conversation_update or handle_message in app/bot/activity_handler.py
→ discover_channel_from_activity
→ extract_teams_context plus authoritative checks in app/utils/teams_context.py
→ record_discovered_teams_channel in app/services/backend_client.py
→ POST BACKEND_BASE_URL/api/teams/channels/discover
→ backend TeamsDiscoveredChannelService.discover
→ Mongo discovered-channel upsert/availability state
→ GET backend /api/teams/channels/{accountId} can report status available.

The bot passes conversationId when present, but discovery does not use it to send notifications and does not create a destination.

# 12. Explicit Connect Flow

Frontend/UI
→ POST backend /api/teams/channels/{accountId}/connect with tenantId, teamId, channelId
→ backend TeamsDiscoveredChannelService.connect verifies an available discovery and enabled Team installation
→ TeamsConversationResolver.resolve POSTs to bot /api/internal/teams/resolve-channel-conversation with tenantId, teamId, channelId, serviceUrl and optional internal key
→ bot ChannelResolutionRequest validates four nonempty strings
→ ConversationService.resolve_channel_conversation builds ConversationParameters
→ adapter.create_conversation sends a readiness message through the Bot Framework connector
→ callback captures Microsoft's returned conversation.id
→ bot returns conversationId
→ backend builds TeamsChannelDestinationCreate with trigger stratsync_ui_connect and source microsoft_create_conversation
→ TeamsChannelDestinationService.register upserts destination
→ backend returns success and serialized destination.

Errors: unavailable discovery is 404; disabled/missing installation is 409; backend-to-bot HTTP/JSON/missing-ID failure becomes backend 502; bot request model failure is 422; bot connector exceptions currently escape as 500; no returned conversation ID raises RuntimeError. The bot route does not validate the serviceUrl origin beyond nonempty text.

Discovery does NOT equal connection. Enumeration, selected-channel installation, channelMemberAdded, channelCreated, normal channel conversation updates, and messages only create available state. Only explicit StratSync UI Connect resolves a Microsoft conversation and registers or re-enables a destination.

# 13. Proactive Notification Flow

n8n POST /api/notifications
→ optional key check
→ _parse_payload
→ NotificationService.handle_initial_notification or handle_action_result
→ card builder
→ NotificationService._send
→ send_to_conversation in app/bot/proactive_sender.py
→ Activity(message, Adaptive Card attachment)
→ ConversationReference(agent and user both configured bot ID, channel msteams, supplied serviceUrl, supplied conversationId and tenantId)
→ get_continuation_activity
→ adapter.continue_conversation
→ callback TurnContext.send_activity
→ Bot Framework connector POST
→ returned activity ID
→ NotificationResponse.

The destination data comes entirely from the notification request: destinationId is optional metadata; tenantId, teamId, conversationId, and serviceUrl are required; channelId is optional. The in-memory ConversationStore is not consulted during proactive delivery.

MSAL uses MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD, and MICROSOFT_TENANT_ID to acquire an application token for connector operations. The SDK attaches it to requests to serviceUrl. This is connector auth, not Graph.

Cards:

- initial_notification → build_initial_risk_card.
- risk_action_result → dynamic_card, risk_details, mitigation_plan, tracking_confirmation, or assignment_confirmation.
- Cards use Adaptive Card schema 1.5 and are sent as new messages; code does not update the original card.

Success logs the connector message ID and returns 200. Any send exception is normalized by classify_teams_error: 429 and Microsoft 5xx are retryable; recognized missing conversation/channel and certain 403 permission failures are permanent; Python TimeoutError/ConnectionError are retryable; unknown errors are conservatively retryable. The route maps permanent to 410 and retryable to 503 without returning the raw exception. ChannelNotRegisteredError is retained but current sender never raises it.

# 14. Backend Client

The FastAPI lifespan owns one shared `httpx.AsyncClient`, so installation enumeration reuses its connection pool across per-channel persistence calls. Direct unit/library calls outside the lifespan use a short-lived fallback client. URLs use `BACKEND_BASE_URL` without a trailing slash. `INTERNAL_API_KEY` is sent as `X-Internal-API-Key` when configured; disconnect refuses to call without it.

| Function | Method/path | Payload | Success handling | Failure handling |
|---|---|---|---|---|
| register_teams_installation | POST /api/teams/installations | Extracted Teams context + botAppId + enabled | JSON installation.accountId or true | 409 logs teams_tenant_not_mapped and false; HTTP/JSON errors log and false. |
| register_teams_destination | Compatibility client for POST /api/teams/channel-destinations; no registered bot lifecycle handler calls it | Destination payload | DestinationRegistrationResult with status, ID, enabled, disconnectReason | Retained for compatibility tests; explicit UI Connect creates destinations inside the backend service. |
| record_discovered_teams_channel | POST /api/teams/channels/discover | tenant/team/name/aadGroup/channel/name/conversation/service/available | true after raise_for_status | HTTP/JSON errors log and false. |
| disconnect_teams_installation | POST /api/teams/installations/disconnect | tenantId, scope, available teamId/channelId/conversationId | disconnected or not_found literal | Missing internal key, invalid scope identity, HTTP/JSON error → failed. |

There are no GET calls, Graph calls, retries, backoff, or accountId values in bot registration payloads.

# 15. Teams Context Utilities

app/utils/teams_context.py supports both plain dict payload fragments and SDK model objects:

- _value: dict.get or getattr without vars.
- _first_value: first non-None alias, supporting snake_case and camelCase.
- _safe_structural_metadata: recursively retains primitives/dicts/lists, uses model_dump for SDK/Pydantic models, and otherwise reports only runtimeType. It never introspects arbitrary __dict__ state.
- installation_update_diagnostic: non-secret installation shape including action, conversation, Team/channel, selected-channel settings, and tenant.
- extract_explicit_install_channel: searches settings.selectedChannel, direct selectedChannel, channelData.channel, then a clearly channel-like installation conversation. Requires ID and name; protects equal Team/channel ambiguity.
- channel_metadata_diagnostic: shape flags, conversation type, event type, and name/channel resolution sources.
- resolve_authoritative_channel: channelData.channel, teamsChannelId, settings.selectedChannel, direct selectedChannel with ambiguity checks.
- has_authoritative_channel_conversation: requires tenant, Team, channel, conversation, service URL, conversationType channel, and conversation ID equal to channel ID.
- extract_teams_context: normalized identity, names, service URL, aadGroupId, channel source, and actor fields.

The historical vars(dict) failure mode is avoided: current code never calls vars on activity metadata. Dicts are read directly and SDK models through getattr/model_dump.

# 16. Identity Model

| Identifier | Source and meaning | Canonical/use/validation |
|---|---|---|
| tenantId | channelData.tenant.id, fallback conversation.tenant_id/tenantId | Microsoft tenant/account mapping key; required for persistence/sends. Not explicitly compared to configured tenant by app code. |
| teamId | channelData.team.id, fallback teamsTeamId | Canonical Bot Framework Team identity. Used with tenant/channel for backend keys. Never replaced by aadGroupId. |
| channelId | Authoritative channel candidates in §9 | Canonical channel identity only when provenance checks pass. Equal to teamId is allowed only with explicit channel metadata, notably General. |
| conversationId | activity.conversation.id or Microsoft's create_conversation result | Actual connector route. For incoming authoritative channel routes it must equal channelId; a different ID is accepted by backend only with microsoft_create_conversation provenance. |
| aadGroupId | channelData.team.aadGroupId/aad_group_id | Optional Entra metadata retained for discovery; not routing identity and never used for Graph. |
| serviceUrl | activity.service_url/serviceUrl or discovered record sent back by backend | Connector endpoint for create/continue. Required but not origin-validated. |
| recipient.id | activity.recipient.id | Identifies this bot for channelMemberAdded verification. |
| membersAdded IDs | activity.members_added items | At least one must equal recipient.id for bot-added channel registration. |
| app/bot ID | MICROSOFT_APP_ID; recipient ID may be a Bot Framework-form ID | JWT audience, AgentApplication bot ID, conversation agent/user account, outbound app identity. |
| actor IDs | activity.from_property id/aad_object_id | Forwarded as connectedBy metadata or ActionActor. Does not prove administrator/owner status. |
| destinationId | Backend Mongo-derived opaque ID | Optional notification metadata and UI disconnect/reconnect selection; not a Teams identifier. |

Bot Framework teamId remains canonical.

# 17. Team Name Handling

Bot extraction obtains teamName only from current channelData.team.name. It does not call Graph.

The adjacent backend discovery implementation resolves teamName in this exact priority:

1. Current discovery activity payload teamName.
2. Existing enabled/local Team installation teamName.
3. A previously named discovered channel for the same account/tenant/team.
4. An existing destination with a teamName for the same tenant/team.
5. None; it logs resolution failure.

When a name is resolved, backend backfills discovered-channel records for the canonical accountId + tenantId + teamId where teamName is null/missing. Destination registration similarly uses current channel activity name, then installation name; repository upsert preserves omitted metadata because the service drops blank name fields.

No Microsoft Graph lookup is used.

# 18. Destination Behavior

- Discovery is triggered by channelCreated, authoritative channel conversation updates, explicit install selection, channelMemberAdded context, and authoritative messages.
- Destination registration is triggered only by explicit StratSync UI Connect. The legacy-named `capture_channel_destination_from_activity` compatibility wrapper delegates to discovery and cannot create a destination.
- channelCreated, ordinary/generic conversationUpdate, Team member changes, messages, and the word connect do not create a destination.
- The bot never automatically connects every discovered channel.
- Backend destination identity is accountId + tenantId + teamId + channelId and is upserted, so duplicate lifecycle calls reuse a record.
- Backend preserves manual_disconnect/manual_removal against lifecycle registration. The bot receives the disabled destination and avoids saving it locally.
- Rediscovery updates availability/name metadata but does not alter destination connection state.
- UI reconnect through /channel-destinations/{accountId}/{destinationId}/reconnect re-enables the same manually disconnected record.
- Team-uninstalled records cannot be UI-reconnected; app reinstall is required.
- Explicit UI Connect resolves a conversation then registers with stratsync_ui_connect. Current backend preservation logic only exempts explicit_connect and explicit_reconnect from manual-disconnect preservation, not stratsync_ui_connect. Therefore using the Connect endpoint on an already manually disconnected record may return the still-disabled record; the dedicated reconnect endpoint is the proven restoration path. This trigger mismatch is technical debt.
- A channel disconnect command sends exact Team/channel scope. Team uninstall uses Team scope and disables all Team destinations.
- The five-second IdempotencyStore applies only to card clicks, not lifecycle activities. Lifecycle idempotency comes from backend upserts.

# 19. Internal API Security

_verify_internal_api_key reads INTERNAL_API_KEY. Production startup requires the key, so production internal requests always require a matching X-Internal-API-Key. Development may remain permissive when blank. hmac.compare_digest supplies constant-time comparison.

Protected bot routes:

- POST /api/notifications.
- POST /api/internal/teams/resolve-channel-conversation.

POST /api/messages uses Microsoft JWT instead, and /health/docs are public.

Outbound use:

- Bot sends the key to backend registration/discovery/destination endpoints when configured.
- Bot refuses backend disconnect when it is absent.
- Bot sends it to n8n action webhook when configured.
- Backend retains INTERNAL_API_KEY_ENABLED for development, but APP_ENV=production forces enforcement and requires a configured key in both services.

The trust boundary is backend/n8n → bot. A holder can cause Teams sends or Microsoft channel conversation creation for caller-supplied identifiers/service URL. The shared key is not tenant-scoped and has no request timestamp/replay signature.

# 20. N8N / Actions

The only direct bot-to-n8n call is N8nService.send_action_event to the exact N8N_ACTION_WEBHOOK_URL; there are no appended webhook paths.

Teams Action.Execute
→ POST /api/messages invoke adaptiveCard/action
→ riskId/actionKey extraction
→ duplicate check
→ RiskActionEvent with generated UUID, current destination, actor, and remaining button data
→ HTTP POST webhook.

Headers are Content-Type application/json, X-Correlation-ID equal to eventId, and optional X-Internal-API-Key. Timeout is N8N_TIMEOUT_SECONDS.

Wire payload:

| Field | Contents |
|---|---|
| eventId | Generated UUID per non-duplicate invoke. |
| riskId/actionKey | Required button data. |
| destination | Current tenantId, optional teamId/channelId, required conversationId/serviceUrl. |
| actor | Teams from account ID/name/aadObjectId when available. |
| payload | Other action.data fields, excluding riskId/actionKey. |

2xx/redirect statuses below 300 count as success. Timeout, network errors, missing URL, and any status 300 or above raise N8nActionWebhookError. The invoke outer response is still an SDK InvokeResponse status 200 containing an Adaptive Card statusCode 502 and a safe user message on failure. There are no retries.

n8n-to-bot notification flow is §13. POST /api/notifications accepts initial_notification and risk_action_result only.

# 21. Logging and Observability

Logs go to stdout as timestamp, level, logger, message. `log_event` only appends reviewed operational fields. It excludes authorization data, secrets, service URLs, message text, raw card data, and full activity bodies.

Important event messages:

| Event | Emission |
|---|---|
| Starting... / Shutting down... | FastAPI lifespan. |
| teams_conversation_update_received | Every conversationUpdate before routing. |
| teams_installation_update_add_metadata | Every installation add with safe structural diagnostic. |
| teams_channel_metadata_found / teams_channel_name_missing | Installation extraction. |
| teams_installation_metadata_extracted / teams_installation_registered | Before/after backend install registration. |
| teams_tenant_not_mapped / teams_installation_registration_failed | Backend install 409 or transport/JSON failure. |
| teams_team_installation_registered | Team-only add succeeded. |
| teams_channel_discovered_not_connected | channelCreated was persisted but not connected. |
| teams_channel_discovery_persistence_failed | Backend discovery failure. |
| teams_channel_member_added_received / teams_channel_member_added_bot_verified | Verified member path stages. |
| teams_channel_registration_skipped | Missing selection/context, wrong event/member, resolution failure, manual removal, or backend rejection. |
| teams_channel_destination_backend_response/succeeded/registration_failed | Destination HTTP call. |
| teams_conversation_reference_captured | Process-local route save. |
| teams_disconnect_command_received / teams_channel_disconnect_requested/failed | Message disconnect path. |
| teams_app_removal_received / teams_installation_disconnect_requested/succeeded/not_found/failed | Uninstall path. |
| teams_notification_received / teams_notification_sent | Notification ingress and the single delivery success event. |
| teams_notification_send_failed | Proactive exception. |
| teams_adaptive_card_action_forwarding/duplicate/invalid | Invoke processing. |
| n8n_action_webhook_timed_out/network_failed/rejected/succeeded | Webhook outcome. |
| unsupported_dynamic_section_type | Dynamic fallback. |

Reason, result, event/card subtype, retryability, and enumeration counters are allowlisted. Human-readable Team/channel names and detailed installation shapes remain excluded. Raw `POST /api/messages` bodies are never logged. There are no application metrics/traces, alert rules, request IDs for all routes, or health dependency checks.

# 22. Error Handling

| Failure | Behavior |
|---|---|
| Missing/invalid Teams JWT or invalid audience | SDK 401; handler not run. |
| Malformed notification event/schema | Router 400 with Pydantic/value detail. Malformed JSON before parsing is framework behavior, generally 400/422. |
| Wrong internal key | 401. |
| Backend registration/discovery HTTP, timeout, JSON | Logged and returned false/failed; Teams activity normally still gets 200. |
| Backend unmapped tenant | Install 409 converted to false; discovery 409 becomes caught HTTP failure/false. |
| Backend disconnect without key | No HTTP call; failed result. |
| n8n timeout/network/non-2xx/missing URL | Controlled invoke message, embedded 502 for the Adaptive Card protocol. |
| Unsupported action-result card | Notification 400. |
| Proactive 429/5xx/network | Notification 503 with safe retryable detail. |
| Missing conversation/channel/permission | Notification 410 when classifier recognizes it. |
| Legacy ChannelNotRegisteredError | Notification 404, though current sender has no raise site. |
| create_conversation failure | Selected-install path logs/skips; internal route has no mapping and normally returns 500; backend resolver converts non-2xx to 502. |
| Microsoft returns no conversation ID | RuntimeError; same route behavior. |
| Malformed lifecycle activity | Extraction returns null fields; operations skip. |
| Unrecognized invoke | Acknowledged 200 without work. |
| Unhandled /api/messages exception | No application global handler; FastAPI/SDK response is unclear from current code for every exception type. |

No outbound call retries, circuit breaker, queue, dead-letter store, or transactional cross-service boundary exists.

# 23. Security Review

## Implemented Security

- Agents SDK JWT decorator on Teams ingress with signature/time/audience validation.
- Production credentials are environment-loaded and .env is gitignored.
- MSAL client-secret flow for outbound connector tokens.
- Constant-time internal-key comparison.
- Pydantic validation for internal payloads.
- Safe error bodies for proactive send failures.
- Allowlisted structured logging helper.
- Non-root UID 1000 container.
- Bot buttons contain riskId/actionKey, not the full risk object.
- Backend account mapping is based on tenantId, and destination keys are account-scoped.

## Risks

| Severity | Evidence and impact |
|---|---|
| Critical configuration | Blank INTERNAL_API_KEY opens notification and conversation-resolution routes even in production. An attacker with network access could request Teams sends/create-conversation attempts. |
| Resolved | POST /api/messages logs only an allowlisted activity envelope and excludes raw user/card content. |
| High | serviceUrl is caller/activity supplied and only checked for nonempty text; connector use creates an SSRF/trust-boundary concern whose exploitability depends on SDK/network controls. |
| High | No explicit application tenant allowlist or comparison between JWT/configured tenant and activity tenant. Backend mapping helps data ownership but occurs after ingress. |
| High | Shared internal key is global, optional, not tenant-scoped, and lacks replay protection. |
| High availability | No durable queue/retry; transient backend, n8n, or Microsoft errors lose that attempt. |
| Medium | Five-second idempotency and conversation references are process-local and reset on restart/replica split. |
| Medium | Public docs/schema and health endpoints; no app-level rate/body limits. |
| Medium | Inbound JWT behavior is delegated to a pinned SDK but has no repository test; current SDK code manually checks audience and key source, while app adds no issuer/tenant policy. |
| Medium | Compose binds bot/backend to loopback, but a public HTTPS ingress required by Teams is not defined here. |
| Low | Operational tenant/team/channel identifiers are logged and need retention/access controls. |

## Recommendations

1. Fail startup outside development unless Microsoft credentials, INTERNAL_API_KEY, backend URL, and required webhook are valid.
2. Preserve tests that prohibit raw activity/card logging.
3. Validate serviceUrl against Microsoft's documented Bot Framework service URL trust mechanism/allowlist and restrict egress.
4. Add explicit supported-tenant policy and verify activity tenant against authenticated claims where appropriate.
5. Replace the shared key with service identity or signed, timestamped requests; at minimum rotate and tenant-scope it.
6. Add edge TLS, authentication-aware rate/body limits, and restrict OpenAPI UI in production.
7. Add durable delivery/retry/idempotency and shared storage for multi-replica operation.
8. Add live non-production JWT, MSAL, connector, n8n, backend-contract, and negative security tests.
9. Add dependency/container scanning and a deployment secret store; these are unclear from current code.

# 24. Docker and Deployment

Dockerfile:

- Base python:3.12-slim.
- WORKDIR /app.
- Installs curl through apt, then deletes apt lists.
- Copies requirements.txt and installs exact direct dependencies without pip cache.
- Copies only app into the image; tests, .env, README, and docs are excluded.
- Creates appuser UID 1000, changes /app ownership, and runs non-root.
- Exposes 3978.
- Starts one Uvicorn process at 0.0.0.0:3978.
- Defines a curl-based `/health` Docker HEALTHCHECK.

Adjacent backend/docker-compose.yml defines mongo, backend, and teams-bot on the default internal Compose network. risk-teams-bot depends on backend, receives BACKEND_BASE_URL=http://backend:8000, and is bound to host loopback 127.0.0.1:3978. Backend receives TEAMS_BOT_BASE_URL=http://teams-bot:3978. Both share the substituted INTERNAL_API_KEY. Mongo is internal-only. `depends_on` backend does not wait for a backend health condition.

Expected topology:

Microsoft Teams/Bot Framework
→ external HTTPS edge/tunnel/reverse proxy not defined in repository
→ loopback/container port 3978
↔ backend over Compose DNS
→ Mongo

n8n reaches /api/notifications through an operator-defined route, and both bot and backend make outbound n8n/Microsoft calls. TLS, DNS, certificates, image registry, CI/CD, replicas, backup, rollback, and production ingress are unclear from current code.

Safe commands:

    cd /path/to/MVP/teams-bot
    docker build -t risk-teams-bot .
    docker run -d --name risk-teams-bot --restart unless-stopped --env-file .env -p 127.0.0.1:3978:3978 risk-teams-bot
    docker logs --tail 200 -f risk-teams-bot
    curl --fail http://127.0.0.1:3978/health

Compose from backend:

    cd /path/to/MVP/backend
    docker compose build teams-bot
    docker compose up -d teams-bot
    docker compose restart teams-bot
    docker compose logs --tail 200 -f teams-bot
    curl --fail http://127.0.0.1:3978/health

For a changed image, prefer docker compose up -d --build teams-bot rather than restart alone. Do not place secrets in command history; use protected environment/secret injection.

# 25. Microsoft Graph Status

The entire current teams-bot tree was searched for:

- graph.microsoft.com
- Channel.ReadBasic.All
- Team.ReadBasic.All
- GroupMember.Read.All
- oauth2/v2.0/token
- .microsoft.com/.default
- list-channels
- teamAadGroupId

None occur in current application/test/documentation files. The only related audience string is https://api.botframework.com/.default in ConversationService, which is Bot Framework Connector scope, not Graph. aadGroupId occurs as optional metadata, not teamAadGroupId and not a lookup key.

Microsoft Graph is not required by the current teams-bot runtime.

The current model avoids Graph application permissions/admin consent. On installation it enumerates existing Team channels through `TeamsInfo.get_team_channels`; later `channelCreated` and authoritative activity discovery keep state current. The backend sync endpoint remains a database-local no-op.

# 26. Tests

Verified command:

    PYTHONPATH=. .venv/bin/pytest -q

Result on 2026-08-25 after the production-hardening refactor: 140 passed in 1.06 seconds, with one StarletteDeprecationWarning about TestClient/httpx. `PYTHONPATH=.` remains required for the documented command.

| Test file | Collected cases | Purpose and major cases |
|---|---:|---|
| tests/test_health.py | 1 | Exact /health status/body. |
| tests/test_installation.py | 66 | Dict/SDK extraction; Team ID/aad metadata; install payload; unmapped tenant; remove and key behavior; explicit selected channel and General; Team-level fake prevention; generic/channelCreated/deleted discovery; no resolution on channelCreated; duplicate events; bot versus human channelMemberAdded; teamMemberAdded skip; stable multi-scope identities; removal events; authoritative conversation checks; personal/group/meeting rejection; backend destination call; message discovery; connect command unsupported; disconnect exact scope. |
| tests/test_channel_enumeration.py | 11 | Existing-channel enumeration, General normalization, whitespace rejection, partial persistence failure, installation failure isolation, and lifespan client reuse. |
| tests/test_security.py | 11 | Safe activity metadata, production key requirement, and accepted/rejected service URLs. |
| tests/test_adaptive_card_invoke.py | 2 | JSON-serializable successful invoke and five-second duplicate response/n8n suppression. |
| tests/test_notifications.py | 26 | Initial/action schemas, legacy vessel adapter, nullable channel ID, required conversation/service, action wire format and actor/destination, n8n success/non-2xx/network, route successes/400/404, permanent/retryable error normalization (including HTTP response status), and internal key rejection. |
| tests/test_proactive_sender.py | 3 | Supplied and Microsoft-resolved conversation continuation, no create during normal send, and exact create_conversation parameters/audience/returned ID. |
| tests/test_cards.py | 14 | Currency/date formatting, initial entity/metrics/severity/buttons, risk details, mitigation isolation/empty arrays. |
| tests/test_dynamic_card.py | 6 | Dynamic route, all section types/order, arbitrary entity, sparse input, unknown-section fallback/logging, and legacy renderers. |
| tests/conftest.py | 0 | Deterministic safe environment setup. |

Coverage requested in the task:

- Health: covered.
- Installation add/remove: covered.
- channelCreated/channelDeleted/channelRemoved: covered.
- channelMemberAdded/teamMemberAdded: covered.
- Fake-channel prevention: covered.
- Duplicate channel events/backend-upsert intent: covered; direct backend integration proves idempotent persistence in adjacent tests.
- Message discovery: covered.
- Conversation resolution: service method covered; the bot HTTP resolution route and its internal key are not directly tested.
- Disconnect/reconnect preservation: bot disconnect covered; full preservation/reconnect behavior is proved by adjacent backend tests, not teams-bot tests.
- Internal API key: notification and outbound disconnect/destination headers covered; resolution route key is not directly covered.
- Malformed payloads: notification and many activity shapes covered; malformed raw JSON/global errors are not.
- Inbound JWT, invalid audience, auth 401, real token/MSAL: not covered.
- Live Microsoft, n8n, backend, Docker, load, multi-process, and security tests: absent.

# 27. End-to-End Sequence Flows

## 1. Bot startup

Uvicorn
→ import app.main
→ get_settings
→ get_connection_manager
→ CloudAdapter + AgentApplication + MemoryStorage
→ configure_logging
→ register_handlers
→ FastAPI/router creation
→ lifespan startup log
→ serve.

## 2. App installation into Team

Teams installationUpdate/add
→ /api/messages JWT
→ handle_installation_update
→ installation diagnostic
→ register_installation_from_activity
→ backend /api/teams/installations
→ tenant/account resolution and installation upsert
→ if no explicit channel, stop without channel/destination.

## 3. New channel creation

Teams conversationUpdate channelCreated
→ /api/messages
→ handle_conversation_update
→ discover_channel_from_activity(explicit_event true)
→ backend /api/teams/channels/discover available true
→ log discovered-not-connected
→ return; no create_conversation/destination.

## 4. Channel discovery

Authoritative channel event/message
→ context extraction/proof
→ backend discovery upsert
→ Team name local resolution/backfill
→ unified list status available unless a destination already changes state.

## 5. User Connect

Frontend
→ backend POST /api/teams/channels/{accountId}/connect
→ validate available discovery and installed Team
→ resolver calls bot internal route.

## 6. Conversation resolution

Bot resolve_channel_conversation
→ ConversationParameters for tenant/team/channel
→ adapter.create_conversation with readiness message and Bot Framework audience
→ Microsoft response callback
→ conversationId to backend.

## 7. Destination connected

Backend builds destination with Microsoft-returned route
→ tenant mapping
→ destination upsert
→ enabled true, connected timestamp, disconnect fields cleared unless preservation rule applies
→ destination returned/UI state connected.

## 8. Proactive notification

Backend/n8n orchestration
→ n8n POST /api/notifications
→ validate/render
→ ConversationReference using stored destination
→ MSAL/connector continuation
→ Teams card
→ safe delivery result.

## 9. Disconnect

UI: backend destination disconnect endpoint
→ exact record gets enabled false, manual_disconnect, source stratsync_ui.

Teams command: in-channel disconnect message
→ bot exact tenant/team/channel extraction
→ backend installations/disconnect scope channel
→ backend channel disable behavior.

## 10. Reconnect

UI POST /api/teams/channel-destinations/{accountId}/{destinationId}/reconnect
→ only manual_disconnect/manual_removal accepted
→ same record re-enabled and timestamps reset
→ no Teams reinstall. Message connect is deliberately unsupported.

## 11. App uninstall

Teams installationUpdate/remove
→ bot Team-scoped backend disconnect
→ installation disabled
→ backend disables all Team destinations with team_uninstalled
→ normal manual reconnect rejected until reinstall.

## 12. Message-based channel discovery

Any message in authoritative channel context
→ handle_message
→ discover_channel_from_activity
→ backend available channel upsert
→ if exact disconnect, perform channel disconnect and reply
→ otherwise no reply/no connection.

# 28. Architectural Invariants

The following are supported by current code/tests:

- Bot Framework channelData.team.id remains the canonical teamId; aadGroupId is optional metadata.
- Discovery persistence does not itself create a destination.
- channelCreated is discovery-only and never calls create_conversation or destination registration.
- Team-level install must not fabricate a channel from teamId/conversationId.
- A generic incoming route is authoritative only for conversationType channel with conversationId equal to channelId.
- A named General channel may legitimately have channelId equal to teamId.
- Message connect is unsupported; explicit backend/UI Connect is the resolution path.
- Explicit Connect requires a discovered available channel and enabled Team installation.
- Proactive delivery uses the supplied/stored Microsoft conversationId; it does not fabricate or resolve at send time.
- Backend discovery identity/upsert makes repeated discovery idempotent.
- Backend destination identity/upsert makes repeated lifecycle registration record-idempotent, although the bot still sends duplicate calls.
- Rediscovery/lifecycle registration does not reactivate manual disconnect/removal.
- Dedicated reconnect reuses the same manually disconnected destination.
- Team uninstall stays Team-scoped even if incidental channel metadata exists.
- Card actions are suppressed for five seconds per process using activity ID + risk ID + action key.
- Microsoft Graph is not required by runtime.

The enforced invariant is that no Teams lifecycle event auto-connects. Only the explicit backend/UI Connect operation may create or re-enable a destination.

# 29. Known Limitations

- Existing channels are enumerated during installation through the Teams connector; channels created later are learned through authoritative Teams activities.
- A failed installation enumeration is not retried by the local backend sync endpoint; a later authoritative activity can still discover the channel.
- channelCreated stores availability but cannot be used directly for delivery until explicit Connect/lifecycle registration.
- A removed channel discovery is marked unavailable, but current bot does not directly disable a destination on channelDeleted/channelRemoved.
- Team deletion has no explicit handler.
- Proactive request trusts n8n/backend to send the correct tenant/conversation/service route.
- ConversationStore is in-memory, not used by proactive sending, lost on restart, and not shared.
- Click idempotency is five seconds, process-local, and restart/replica vulnerable.
- No retries or durable delivery for backend, n8n, or Microsoft.
- Internal auth may be disabled when the key is blank only outside production; production startup fails closed.
- serviceUrl has no allowlist/trust validation.
- HOST/PORT settings do not control the Docker command.
- One Uvicorn worker is defined; scaling semantics are not implemented.
- Health reports only process availability, not Microsoft/backend/n8n readiness.
- Assignment input card is not a Teams people picker and is not wired into a current render route.
- Initial card exposes only View Details and Mitigation Plan buttons despite assignment/tracking builders existing.
- Unknown invoke types are acknowledged but unsupported.
- Missed historical uninstall/events cannot be replayed.
- Existing README/docs can lag the current working tree; code/tests are authoritative.

# 30. Technical Debt

## Critical

| Evidence | Impact | Remediation |
|---|---|---|
| Development permits blank INTERNAL_API_KEY. | Local routes are open if a development deployment is exposed. | Keep development private; production startup requires the shared key. |
| app/main.py prints complete inbound activity. | User/action data leakage and uncontrolled logs. | Remove print; add redacted structured event logging. |

## High

| Evidence | Impact | Remediation |
|---|---|---|
| Public HTTPS DNS names are accepted as serviceUrl after local/private target rejection. | DNS rebinding remains an infrastructure-level trust risk. | Restrict production egress to Microsoft connector endpoints and monitor DNS. |
| No durable retry/queue. | Transient lifecycle/action/notification loss. | Durable outbox/queue, bounded retry, idempotent consumers. |
| Process-local dedupe/reference state. | Duplicates and inconsistent replicas/restarts. | Shared Redis/database TTL and persistent route ownership. |
| No explicit activity tenant-to-auth claim policy. | Weaker tenant isolation assurance at ingress. | Validate supported tenants and claim/activity consistency. |
| Explicit UI Connect can re-enable a manually disconnected destination. | Intentional explicit-user behavior; lifecycle discovery remains unable to reconnect it. | Preserve regression tests around trigger provenance. |

## Medium

| Evidence | Impact | Remediation |
|---|---|---|
| Create-conversation internal route lacks exception mapping. | Generic 500 and inconsistent contract. | Safe typed 4xx/502/503 mapping with correlation ID. |
| No direct route/JWT/MSAL tests. | Auth and route regressions can ship. | Component tests with SDK seams and staging E2E. |
| Public docs, no rate/body policy. | Reconnaissance/resource abuse. | Production docs control and edge/app limits. |
| channel deletion does not disable destination in bot path. | Stale connected UI state until send/backend maintenance. | Coordinate explicit unavailable/destination lifecycle policy. |
| HOST/PORT unused. | Deployment surprise. | Wire startup script or remove settings. |

## Low

| Evidence | Impact | Remediation |
|---|---|---|
| ChannelNotRegisteredError has no current raise site. | Misleading 404 branch. | Remove after contract review. |
| conversation_service capture_from_turn_context and get_reference are not called by registered handlers/send path. | Dead/unclear abstraction. | Integrate intentionally or delete. |
| capture_channel_destination_from_activity retains a legacy name but is discovery-only. | The name may confuse maintainers. | Remove after downstream compatibility is confirmed. |
| Existing split docs/README contain stale path/behavior statements. | Operator error. | Make this file authoritative or regenerate docs together. |

# 31. Production Readiness

| Area | Assessment |
|---|---|
| Authentication | Correct SDK mechanism is wired for Teams and MSAL; mandatory production config, explicit tenant policy, service identity, and tests remain blockers. |
| Event handling | Strong defensive extraction and broad unit coverage; teamDeleted/member removal and replay are gaps. |
| Channel discovery | Graph-free installation enumeration plus event-driven updates, idempotent persistence, and fake-channel protection. |
| Explicit Connect | End-to-end architecture exists and backend tests prove it; serviceUrl validation, route error mapping, direct bot-route tests, and trigger mismatch need resolution. |
| Proactive messaging | Correct connector continuation/create patterns and safe failure envelope; live validation, retry, and durable ownership absent. |
| Error handling | Good best-effort lifecycle isolation and send normalization; inconsistent global/internal route behavior and no retry. |
| Logging | Safe allowlisted activity-envelope metadata; raw message/card bodies are not logged. |
| Security | Non-root, JWT, MSAL, production fail-closed internal key, constant-time key comparison, and centralized service-URL validation; tenant policy and DNS/egress controls remain deployment concerns. |
| Deployment | Reproducible pinned non-root Python image with a container healthcheck; no defined public TLS ingress, secret store, CI/CD, rollback, or scaling policy. |
| Tests | 140 fast passing cases cover core logic; all external integrations are mocked and live JWT/MSAL behavior remains untested. |

Ready parts: card rendering/contracts, core FastAPI wiring, defensive activity context logic, Graph-free discovery state, backend upsert integration, proactive connector construction, action forwarding, and unit/component test baseline.

Remaining production blockers:

1. Run real staging Teams install/enumeration/Connect/send/action/uninstall tests.
2. Add production egress restrictions and explicit tenant policy.
3. Define HTTPS ingress, secrets, monitoring, retry/durable delivery, and rollback.

Post-launch improvements include shared idempotency, persistent route storage or clearer backend ownership, richer safe telemetry, dependency scanning, explicit deletion handling, and documented channel-coverage expectations.

# 32. CTO Briefing

## CTO Briefing

## Architecture in 10 bullets

1. One Python/FastAPI/Uvicorn process is the Teams transport layer.
2. Microsoft 365 Agents SDK implements Bot Framework JWT, dispatch, MSAL, and connector operations.
3. The bot owns no risk database or account mapping.
4. Backend owns tenant mapping, installations, discovered channels, destinations, and UI connection state.
5. n8n owns action/notification orchestration.
6. Teams events provide all runtime Team/channel metadata; Graph is absent.
7. Discovery and connected destinations are deliberately separate states.
8. Explicit Connect asks Microsoft to create/resolve a channel conversation before destination creation.
9. Proactive sends continue an existing caller-supplied conversation route.
10. Local stores are volatile optimizations/abstractions, not durable system state.

## Exact Teams lifecycle

Install add → register Team → enumerate existing channels → optionally discover an explicitly selected channel. Verified bot channelMemberAdded, channelCreated, generic channel activity, and message → discovery only. Explicit UI Connect → resolve Microsoft conversation → destination upsert. Channel remove/delete → unavailable discovery. Disconnect command → exact channel soft-disconnect. Installation remove → Team soft-disconnect/all Team destinations disabled.

## Exact channel discovery flow

Teams authoritative activity → /api/messages → registered activity handler → extract/prove context → bot backend client → /api/teams/channels/discover → tenant mapping → discovered-channel upsert → available UI state.

## Exact Connect flow

UI → backend /channels/{accountId}/connect → verify discovery/install → bot internal resolve route → Bot Framework create_conversation → Microsoft conversationId → backend destination upsert → connected state.

## Exact notification flow

Backend/n8n job → /api/notifications → key/schema → card renderer → ConversationReference → MSAL/Connector continue_conversation → Teams message → normalized delivery response.

## Why Graph is not required

Current code learns Teams identities and names from Bot Framework activity channelData, `TeamsInfo.get_team_channels`, and local backend records. Connector APIs enumerate, resolve, and send conversations without Graph permissions or administrator consent.

## Top 5 strengths

1. Clear service boundary with no risk-data access.
2. Defensive dict/SDK context extraction and fake-channel protections.
3. Enforced separation of lifecycle discovery, explicit UI connection, and destination state.
4. Broad fast test suite with 117 passing cases.
5. Modern supported SDK, pinned dependencies, non-root container, and safe delivery error envelope.

## Top 5 risks

1. Internal mutation routes are open when the shared key is blank.
2. Raw Teams activity bodies are printed.
3. Caller-supplied serviceUrl and weak explicit tenant policy.
4. No durable retries/shared idempotency; mocked-only integration validation.
5. Production ingress, secrets, monitoring, rollback, and scaling are undefined.

## Production limitations

Channel coverage is populated at installation and updated by later events, but failed installation enumeration has no durable retry. Delivery depends on stored Microsoft routes. Process-local state is replica-unsafe. Team deletion/removal subtypes are incomplete. Real tenant, token, and connector behavior remains unproven by this suite.

## Recommended next improvements

First enforce/redact security controls and fix the Connect/reconnect trigger mismatch. Then run a staged real-Teams lifecycle test and implement trusted URL/tenant validation. Next add durable retry/shared idempotency and full operational deployment controls. Finally improve deletion handling, pooled clients, safe observability, and live contract/security tests.
