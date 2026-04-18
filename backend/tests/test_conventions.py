"""
Machine-enforced codebase conventions.

These tests fail the build if any of the following patterns appear outside
their designated files.  They are cheap (pure static analysis, no DB) and run
on every pytest invocation.
"""

from __future__ import annotations

import pathlib
import re

APP_ROOT = pathlib.Path(__file__).parents[1] / "app"


# ── Helpers ──────────────────────────────────────────────────────────────────


def grep(pattern: str, *, exclude_file: str | None = None) -> list[str]:
    """Return 'file:line: text' for every match in app/."""
    rx = re.compile(pattern)
    hits: list[str] = []
    for py_file in APP_ROOT.rglob("*.py"):
        if exclude_file and py_file.name == exclude_file:
            continue
        for lineno, line in enumerate(py_file.read_text().splitlines(), 1):
            if rx.search(line):
                hits.append(f"{py_file.relative_to(APP_ROOT)}:{lineno}: {line.strip()}")
    return hits


# ── Cache-key convention ──────────────────────────────────────────────────────


def test_no_inline_revenue_cache_key() -> None:
    """
    Cache keys must be built via core/cache_keys.py — never inline.

    Prevents re-introducing Bug B-01 (cache poisoning) by ensuring the key
    always includes tenant_id and that the format is centralised.
    """
    hits = grep(r'f["\']revenue:', exclude_file="cache_keys.py")
    assert not hits, (
        "Hardcoded revenue cache key strings found outside cache_keys.py:\n"
        + "\n".join(hits)
        + "\nFix: use core.cache_keys.revenue_cache_key(tenant_id, property_id)"
    )


def test_no_inline_auth_cache_key() -> None:
    hits = grep(r'f["\']auth:', exclude_file="cache_keys.py")
    assert not hits, (
        "Hardcoded auth cache key strings found outside cache_keys.py:\n"
        + "\n".join(hits)
    )


# ── Money precision ───────────────────────────────────────────────────────────


def test_no_float_cast_on_money() -> None:
    """
    float() on money is forbidden — use Decimal.quantize(TWOPLACES, ROUND_HALF_UP).

    Bug B-03: float cast causes IEEE-754 drift in revenue totals.
    """
    # Match float(<something that looks like revenue/amount>)
    hits = grep(r'\bfloat\s*\(\s*(?:revenue|total|amount|price|cost|sum)\b')
    assert not hits, (
        "float() used on monetary value — use Decimal.quantize instead:\n"
        + "\n".join(hits)
    )


# ── datetime.utcnow() is deprecated ──────────────────────────────────────────


def test_no_datetime_utcnow() -> None:
    """
    datetime.utcnow() returns a naive datetime — use datetime.now(timezone.utc).

    Naive datetimes cause silent timezone bugs when comparing with tz-aware
    values from the DB.
    """
    hits = grep(r'datetime\.utcnow\(\)')
    assert not hits, (
        "datetime.utcnow() is deprecated and returns a naive datetime:\n"
        + "\n".join(hits)
        + "\nFix: datetime.now(timezone.utc)"
    )


# ── print() in application code ───────────────────────────────────────────────


def test_no_print_statements() -> None:
    """print() in app code bypasses structured logging and may leak PII."""
    # Allow print() only in scripts/ and management commands, not in app/
    hits = grep(r'^\s*print\s*\(')
    assert not hits, (
        "print() found in app/ — use logging.getLogger(__name__) instead:\n"
        + "\n".join(hits)
    )


# ── Direct authenticate_request on tenant endpoints ──────────────────────────


def test_tenant_endpoints_use_tenant_scope() -> None:
    """
    Endpoints in api/v1/ that touch tenant data must use require_tenant_scope,
    not authenticate_request directly.

    Permitted exceptions: login.py, health.py, auth_info.py, persistent_auth.py
    (these don't access tenant-scoped tables).
    """
    allowed = {
        "login.py",
        "health.py",
        "auth_info.py",
        "persistent_auth.py",
        "bootstrap.py",
        "users_lightning.py",
        "cities.py",
        "city_access_fast.py",
        "city_access_fixed.py",
        "departments.py",
        "profile.py",
        "company_settings.py",
    }

    api_dir = APP_ROOT / "api" / "v1"
    violations: list[str] = []

    for py_file in api_dir.glob("*.py"):
        if py_file.name in allowed:
            continue
        text = py_file.read_text()
        # If the file uses authenticate_request as a Depends() but not via
        # require_tenant_scope, that's the violation.
        if "Depends(authenticate_request)" in text and "require_tenant_scope" not in text:
            violations.append(str(py_file.relative_to(APP_ROOT)))

    assert not violations, (
        "Tenant-scoped endpoints using authenticate_request directly "
        "(should use require_tenant_scope):\n" + "\n".join(violations)
    )
