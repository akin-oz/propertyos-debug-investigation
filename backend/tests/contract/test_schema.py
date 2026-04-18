"""
Static schema assertions — no running server required.

These tests run on every PR and every release:
  pytest tests/contract/test_schema.py

They assert the *committed* openapi.json matches what the live FastAPI app
would generate, and that the critical `total_revenue` contract is locked.
"""

import json
import pathlib
import re
import os

import pytest

SCHEMA_PATH = pathlib.Path(__file__).parents[2] / "openapi.json"
APP_SCHEMA_PATH = SCHEMA_PATH  # kept as alias for clarity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _strip_operation_ids(schema: dict) -> dict:
    """
    Remove auto-generated operationId values before comparing schemas.

    FastAPI assigns operationId by combining the function name, path, and HTTP
    method.  When a route is registered with both GET and HEAD
    (`@app.api_route("/health", methods=["GET","HEAD"])`), the method suffix
    (_get vs _head) is assigned non-deterministically between Python runs.

    Stripping operationIds still catches all meaningful drift — new fields,
    type changes, removed paths — without false-positive failures.
    """
    import copy

    s = copy.deepcopy(schema)
    for path_item in s.get("paths", {}).values():
        for op in path_item.values():
            if isinstance(op, dict):
                op.pop("operationId", None)
    return s


def resolve_ref(schema: dict, ref: str) -> dict:
    """Walk a $ref pointer like '#/components/schemas/Foo'."""
    parts = ref.lstrip("#/").split("/")
    node = schema
    for part in parts:
        node = node[part]
    return node


def get_response_schema(schema: dict, path: str, method: str = "get") -> dict:
    endpoint = schema["paths"][path][method]
    resp = endpoint["responses"]["200"]["content"]["application/json"]["schema"]
    if "$ref" in resp:
        return resolve_ref(schema, resp["$ref"])
    return resp


# ---------------------------------------------------------------------------
# Schema drift: committed file == live app output
# ---------------------------------------------------------------------------

def test_committed_schema_matches_app_output():
    """
    Drift detection: regenerate the schema from the live FastAPI app and
    compare it byte-for-byte against the committed openapi.json.

    Fail message tells the developer exactly what to run.
    """
    os.environ.setdefault("SUPABASE_URL", "http://placeholder.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "placeholder-anon-key")
    os.environ.setdefault("SECRET_KEY", "placeholder-secret-for-schema-export")

    from app.main import app

    live = _strip_operation_ids(app.openapi())
    committed = _strip_operation_ids(load_schema())

    assert live == committed, (
        "OpenAPI schema drift detected!\n"
        "The committed openapi.json no longer matches the FastAPI app.\n"
        "Fix: cd backend && uv run python scripts/export_schema.py && git add openapi.json"
    )


# ---------------------------------------------------------------------------
# total_revenue contract — locked type
# ---------------------------------------------------------------------------

def test_total_revenue_is_string_not_number():
    """
    B-03 / precision contract: total_revenue must be 'type: string' in the
    OpenAPI schema so that TypeScript clients never treat it as a float.
    """
    schema = load_schema()
    dashboard_schema = get_response_schema(schema, "/api/v1/dashboard/summary")
    prop = dashboard_schema["properties"]["total_revenue"]

    assert prop.get("type") == "string", (
        f"total_revenue must be 'type: string' (decimal-safe) — got {prop.get('type')!r}.\n"
        "Never use 'type: number' for monetary values; IEEE-754 float drift corrupts sums."
    )


def test_total_revenue_has_decimal_pattern():
    """
    total_revenue must carry a regex pattern that rejects float notation
    (e.g. '1e3', '1000.1234') and enforces exactly two decimal places.
    """
    schema = load_schema()
    dashboard_schema = get_response_schema(schema, "/api/v1/dashboard/summary")
    prop = dashboard_schema["properties"]["total_revenue"]

    pattern = prop.get("pattern", "")
    assert pattern, "total_revenue must have a 'pattern' constraint in the schema"

    compiled = re.compile(pattern)
    # Valid values
    for valid in ("0.00", "1.00", "1234.56", "999999.99"):
        assert compiled.fullmatch(valid), f"Pattern rejected valid value: {valid!r}"

    # Invalid values — float notation or wrong decimal places
    for invalid in ("1e3", "1000", "1000.1", "1000.123", "-1.00", "abc"):
        assert not compiled.fullmatch(invalid), (
            f"Pattern accepted invalid value: {invalid!r}"
        )


def test_total_revenue_is_required():
    """total_revenue must be a required field — never nullable or optional."""
    schema = load_schema()
    dashboard_schema = get_response_schema(schema, "/api/v1/dashboard/summary")
    required = dashboard_schema.get("required", [])

    assert "total_revenue" in required, (
        "total_revenue must be listed in 'required' — optional revenue is a silent data loss bug"
    )


# ---------------------------------------------------------------------------
# currency contract
# ---------------------------------------------------------------------------

def test_currency_is_iso4217_constrained():
    """currency must be a 3-character uppercase string (ISO 4217 pattern)."""
    schema = load_schema()
    dashboard_schema = get_response_schema(schema, "/api/v1/dashboard/summary")
    prop = dashboard_schema["properties"]["currency"]

    assert prop.get("type") == "string"
    assert prop.get("minLength") == 3
    assert prop.get("maxLength") == 3
    assert prop.get("pattern") == "^[A-Z]{3}$", (
        f"currency pattern should be '^[A-Z]{{3}}$', got {prop.get('pattern')!r}"
    )


# ---------------------------------------------------------------------------
# Properties endpoint contract
# ---------------------------------------------------------------------------

def test_properties_response_has_data_array():
    """GET /api/v1/properties must return {data: [...], total: int}."""
    schema = load_schema()
    props_schema = get_response_schema(schema, "/api/v1/properties")

    if "$ref" in props_schema:
        props_schema = resolve_ref(schema, props_schema["$ref"])

    assert "data" in props_schema.get("properties", {}), (
        "PropertiesResponse must have a 'data' array field"
    )
    assert "total" in props_schema.get("properties", {}), (
        "PropertiesResponse must have a 'total' integer field"
    )
