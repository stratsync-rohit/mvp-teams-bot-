"""Validation for Microsoft Bot Framework connector service URLs."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def validate_service_url(value: str) -> str:
    """Return a normalized HTTPS connector URL or reject unsafe endpoints.

    Microsoft uses multiple regional Bot Framework hostnames, so this deliberately
    avoids a brittle single-domain allowlist. It blocks local/internal IP literals,
    local-only hostnames, embedded credentials, fragments, and non-HTTPS schemes.
    Network egress policy should remain the final defense against DNS rebinding.
    """
    if not isinstance(value, str):
        raise ValueError("serviceUrl must be a string")
    normalized = value.strip()
    parsed = urlparse(normalized)
    hostname = parsed.hostname
    if parsed.scheme.lower() != "https" or not hostname:
        raise ValueError("serviceUrl must be an HTTPS URL with a hostname")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("serviceUrl contains unsupported URL components")

    lowered = hostname.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith((".localhost", ".local", ".internal")):
        raise ValueError("serviceUrl must not target a local hostname")
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("serviceUrl must not target a private or local IP address")
    return normalized
