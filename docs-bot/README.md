# Risk Teams Bot: developer documentation

Risk Teams Bot is the Microsoft Teams transport and Adaptive Card rendering service for StratSync risk notifications. It accepts notification commands from n8n, posts cards into existing Teams conversations, receives Teams lifecycle and card-action activities, and synchronizes or forwards them to the backend and n8n. It owns no risk data.

## At a glance

| Area | Implementation |
|---|---|
| Runtime | Python 3.12 container |
| HTTP | FastAPI 0.141.1 and Uvicorn |
| Teams | Microsoft 365 Agents SDK 1.3.0 |
| Validation | Pydantic 2.13.4 / pydantic-settings |
| Outbound HTTP | httpx 0.28.1 |
| Persistence | None; two process-memory stores only |
| Integrations | Microsoft Teams, n8n, StratSync backend |

Start locally with `PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 3978`. See [Local Development](12-LOCAL-DEVELOPMENT.md) before configuring credentials.

## Recommended reading order

1. [Project Overview](01-PROJECT-OVERVIEW.md)
2. [System Architecture](02-SYSTEM-ARCHITECTURE.md)
3. [Codebase Structure](03-CODEBASE-STRUCTURE.md)
4. [Application Flow](04-APPLICATION-FLOW.md)
5. [API Reference](05-API-REFERENCE.md)
6. [Authentication and Authorization](07-AUTHENTICATION-AUTHORIZATION.md)
7. [Services and Business Logic](08-SERVICES-AND-BUSINESS-LOGIC.md)
8. [External Integrations](09-EXTERNAL-INTEGRATIONS.md)
9. [Local Development](12-LOCAL-DEVELOPMENT.md)
10. [Developer Handover](18-DEVELOPER-HANDOVER.md)

## Complete index

- [Database Design](06-DATABASE-DESIGN.md)
- [Webhooks and Events](10-WEBHOOKS-AND-EVENTS.md)
- [Configuration and Environment](11-CONFIGURATION-ENVIRONMENT.md)
- [Deployment and Infrastructure](13-DEPLOYMENT-INFRASTRUCTURE.md)
- [Error Handling and Logging](14-ERROR-HANDLING-LOGGING.md)
- [Testing](15-TESTING.md)
- [Security](16-SECURITY.md)
- [Troubleshooting](17-TROUBLESHOOTING.md)
- [Technical Debt and Improvements](19-TECHNICAL-DEBT-AND-IMPROVEMENTS.md)
