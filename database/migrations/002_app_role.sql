-- Migration 002: Non-superuser application role
--
-- Creates a least-privilege role for the application connection pool.
-- Even if application code is compromised the role cannot:
--   - ALTER / DROP tables
--   - BYPASS RLS
--   - Create new roles or grant superuser
--
-- The RLS policies from migration 001 remain active for this role.
-- Service-level admin operations (migrations, seed data) still run under
-- the superuser role via a separate connection string (DATABASE_ADMIN_URL).
--
-- Apply once against the target database:
--   psql $DATABASE_URL -f database/migrations/002_app_role.sql
--
-- Idempotent: safe to run multiple times.

-- 1. Create role if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'propertyflow_app') THEN
        CREATE ROLE propertyflow_app
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            LOGIN
            PASSWORD 'REPLACE_WITH_GENERATED_SECRET';
    END IF;
END
$$;

-- 2. Grant DML on existing tenant-scoped tables
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE properties, reservations, tenants
    TO propertyflow_app;

-- 3. Grant usage on the public schema so the role can see the tables
GRANT USAGE ON SCHEMA public TO propertyflow_app;

-- 4. Ensure future tables in the schema are also accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO propertyflow_app;

-- 5. Grant EXECUTE on set_config so the role can activate RLS per request
--    (set_config is a built-in; GRANT EXECUTE is not required in PostgreSQL —
--    any user can call it — but documenting the intent here for clarity.)

-- USAGE NOTE:
-- Replace the connection string used by the application pool:
--   DATABASE_URL=postgresql://propertyflow_app:SECRET@host/db
-- Keep the existing superuser URL in DATABASE_ADMIN_URL for migrations only.
