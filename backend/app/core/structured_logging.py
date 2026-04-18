"""
Structured logger for auth, tenant resolution, and cache decisions.

Every security-relevant decision emits exactly one JSON log line with a fixed
set of fields.  Callers cannot invent ad-hoc formats.

Contract:
  - event:      one of AuthEvent (finite, enumerated)
  - tenant_id:  opaque string — never an email address or user-visible name
  - user_id:    opaque UUID — NOT email (email is PII, excluded from logs)
  - request_id: X-Request-ID header value, or None
  - decision:   one of Decision (finite, enumerated)

No PII (email addresses, names, IP addresses) may appear in the `body` field.
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Optional

_base_logger = logging.getLogger("base360.security")


class AuthEvent(str, Enum):
    AUTH_OK = "auth_ok"
    AUTH_DENIED = "auth_denied"
    TENANT_RESOLVED = "tenant_resolved"
    TENANT_MISSING = "tenant_missing"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_POISONED = "cache_poisoned"
    SCOPE_GRANTED = "scope_granted"
    SCOPE_DENIED = "scope_denied"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"


class SecurityLogger:
    """
    Thin wrapper around stdlib logging.  Every call emits a single JSON line.

    Usage:
        from app.core.structured_logging import security_log, AuthEvent, Decision

        security_log.record(
            event=AuthEvent.AUTH_OK,
            user_id=user.id,
            tenant_id=str(scope.tenant_id),
            decision=Decision.ALLOW,
            request_id=request_id,
        )
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def record(
        self,
        event: AuthEvent,
        decision: Decision,
        *,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        extra: Optional[dict] = None,  # type: ignore[type-arg]
    ) -> None:
        entry: dict = {  # type: ignore[type-arg]
            "ts": time.time(),
            "event": event.value,
            "decision": decision.value,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "request_id": request_id,
        }
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 2)
        if extra:
            # Caller is responsible for keeping extra PII-free.
            entry.update(extra)
        self._logger.info(json.dumps(entry))


# Module-level singleton — import this, don't instantiate SecurityLogger yourself.
security_log = SecurityLogger(_base_logger)
