#!/usr/bin/env python3
"""
Export FastAPI OpenAPI schema to openapi.json.

Usage (from the backend/ directory):
    uv run python scripts/export_schema.py

The generated file is committed to the repo.  CI compares the committed copy
against a freshly generated one; a diff fails the build (schema drift).
"""
import json
import os
import pathlib
import sys

# Stub out env vars that would normally come from docker-compose / .env.
# The schema export only traverses route registrations and Pydantic models —
# it never opens a DB connection or calls Redis.
os.environ.setdefault("SUPABASE_URL", "http://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "placeholder-anon-key")
os.environ.setdefault("SECRET_KEY", "placeholder-secret-for-schema-export")

# Ensure the backend package is importable when run from inside backend/
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.main import app  # noqa: E402

schema = app.openapi()

out_path = pathlib.Path(__file__).parent.parent / "openapi.json"
out_path.write_text(json.dumps(schema, indent=2) + "\n")

print(f"✓ Wrote {out_path.relative_to(pathlib.Path(__file__).parent.parent.parent)}")
