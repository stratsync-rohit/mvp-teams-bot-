# Project overview

## Purpose and boundary

This service bridges StratSync risk automation and Microsoft Teams. n8n supplies risk presentation data; the bot renders it as Adaptive Cards and delivers it. Teams supplies installation events and user actions; the bot synchronizes installation context to the backend and forwards actions to n8n.

The service deliberately does **not** score risks, query MongoDB, resolve accounts, or orchestrate mitigation. Those responsibilities belong to systems outside this repository.

## Implemented features

- Health endpoint and Microsoft Teams activity endpoint.
- Internal notification endpoint supporting initial notifications and action results.
- Initial, details, mitigation, assignment, tracking, and schema-driven dynamic cards.
- Proactive delivery into a caller-supplied Teams conversation.
- Teams install/add, remove, conversation-update, message, and Adaptive Card invoke handling.
- Backend synchronization for installations and channel destinations.
- Five-second duplicate-click suppression within one process.
- Optional shared API-key protection for internal calls.

## Actors

| Actor | Role |
|---|---|
| Microsoft Teams / Agents service | Sends bot activities and receives proactive cards |
| Teams user | Installs/removes the app and clicks card actions |
| n8n | Sends notification commands and receives action events |
| StratSync backend | Stores tenant mappings, installations, and channel destinations |
| Operator/developer | Configures credentials, deploys, observes logs |

## Technology roles

| Technology | Purpose |
|---|---|
| FastAPI/Uvicorn | HTTP application and OpenAPI generation |
| Microsoft 365 Agents SDK | JWT validation, activity dispatch, proactive continuation |
| MSAL connection manager | Microsoft access-token acquisition |
| Pydantic | Environment and wire-payload validation |
| httpx | Async calls to n8n and the backend |
| Adaptive Cards 1.5 JSON | Teams presentation format |
| pytest | Unit and HTTP-level tests |
| Docker | Python 3.12 production image |

No queue, scheduler, worker, database, migration system, or background task is implemented.
