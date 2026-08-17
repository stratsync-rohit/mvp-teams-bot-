# Error handling and logging

## HTTP behavior

The notification router maps validation/unsupported events and cards to 400, key failure to 401, legacy channel-not-registered error to 404, and Teams send failure to 502. FastAPI handles unmatched routes, request parsing outside local catches, and framework validation. No global exception handler defines a uniform error envelope.

Teams lifecycle/backend errors are logged and swallowed so Teams processing continues. n8n action failures produce a user-facing invoke message with embedded status 502. There are no retries, circuit breakers, or dead-letter queues.

## Logging

`configure_logging` writes Python logs to stdout as timestamp, level, logger, and message. `LOG_LEVEL` defaults to INFO. `log_event` appends only a whitelist of operational fields, intentionally excluding credentials and payloads.

Important limitation: several calls pass fields such as `error_type`, `card_type`, and `has_connected_by` that are absent from `_SAFE_FIELDS`; those values are silently discarded. Exceptions are generally not logged with stack traces. This reduces diagnostic value.

Use `event_id`, `risk_id`, `correlation_id`, tenant/team/channel/conversation IDs, and message ID to trace a flow. Central log aggregation, retention, metrics, traces, alerts, and request-access logging configuration are not confirmed.
