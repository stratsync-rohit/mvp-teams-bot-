# Security review

## Existing protections

- Agents SDK JWT authorization protects Teams ingress when production credentials are configured.
- Internal key comparison is constant-time.
- Pydantic validates notification/action envelopes.
- MSAL acquires outbound Teams tokens; secrets are environment-driven.
- Structured logging uses a field allowlist and avoids bodies/credentials.
- Container runs as non-root UID 1000.
- Card buttons carry identifiers rather than full risk objects.

## Potential risks

| Severity | Finding | Evidence/impact |
|---|---|---|
| Critical configuration | `/api/notifications` is open whenever the key is blank, even in production | Any caller could request Teams sends |
| High | Destination `serviceUrl` is trusted from notification input | Potential SSRF/trust-boundary exposure depends on SDK handling |
| High | One shared key has no tenant-scoped authorization | A compromised caller can target any supplied destination |
| High | In-memory five-second idempotency is replica-local | Duplicate action execution is possible |
| Medium | Default FastAPI docs/schema remain unauthenticated | Contract reconnaissance |
| Medium | No rate limiting/body-size policy/replay protection | Abuse and resource exhaustion |
| Medium | Dependency pins exist but no vulnerability scan/lock hashes | Supply-chain visibility gap |
| Low | Correlation and tenant identifiers appear in logs | Operational identifiers require retention controls |

## Recommended improvements

Fail startup outside development if credentials, internal key, or required URLs are missing. Validate/allowlist Teams service URLs, use per-service credentials or signed requests with replay protection, enforce tenant/destination authorization, add edge rate/body limits, replace local idempotency with shared atomic TTL storage, restrict API docs in production, and add dependency/container scanning.

TLS termination and network policies are not confirmed from the current codebase.
