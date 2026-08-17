# Authentication and authorization

## Teams ingress

`POST /api/messages` uses the Agents SDK `jwt_authorization_decorator`. `app/config.py` translates `MICROSOFT_APP_ID`, `MICROSOFT_APP_PASSWORD`, and `MICROSOFT_TENANT_ID` into a client-secret `AgentAuthConfiguration`. The same configuration supports outbound MSAL token acquisition.

Anonymous Teams ingress is allowed only when `APP_ENV` is `development`, `dev`, or `local` **and** app ID/password are both absent. If credentials are present, JWT validation is enabled. The exact issuer/audience validation is SDK-owned.

## Internal notification ingress

When `INTERNAL_API_KEY` is non-empty, `/api/notifications` requires an equal `X-Internal-API-Key`; comparison uses `hmac.compare_digest`. When empty, the route is open in every environment—the comment says local/dev, but no environment check enforces that intent.

## Outbound authentication

- n8n receives `X-Internal-API-Key` only if configured, plus `X-Correlation-ID`.
- backend registration calls include the key only if configured.
- backend disconnect refuses to call without the key.
- Teams proactive sends use MSAL through `CloudAdapter`.

## Authorization and tenancy

There are no roles, permissions, account checks, or local tenant-ownership checks. Backend APIs are expected to resolve Microsoft tenant mappings. `/api/notifications` trusts its authenticated caller’s destination, including `serviceUrl`; tenant isolation is therefore delegated to the shared key, backend/n8n orchestration, and Microsoft SDK behavior.

No login/session/JWT issuance flow exists in this service.
