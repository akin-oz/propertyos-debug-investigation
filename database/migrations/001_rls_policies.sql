-- Migration 001: Enable Row Level Security on all tenant-scoped tables
--
-- The original schema enabled RLS on properties and reservations but did not
-- define policies, leaving the tables fully blocked for user-scoped queries
-- (every row invisible). This migration adds:
--
--   1. RLS + policy on tenants     — tenants must not read each other's metadata
--   2. Policy on properties        — with WITH CHECK to block cross-tenant inserts
--   3. Policy on reservations      — with WITH CHECK to block cross-tenant inserts
--
-- All policies key on app.current_tenant_id, which must be set per-session via:
--   SELECT set_config('app.current_tenant_id', <tenant_id>, true);
-- before any user-scoped query. The service role key bypasses RLS entirely,
-- so backend-initiated admin operations are unaffected.
--
-- Idempotent: safe to run multiple times.

-- 1. tenants
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON tenants;
CREATE POLICY tenant_isolation ON tenants
    FOR ALL
    USING (id = current_setting('app.current_tenant_id', true))
    WITH CHECK (id = current_setting('app.current_tenant_id', true));

-- 2. properties
-- ENABLE ROW LEVEL SECURITY already present in schema.sql
DROP POLICY IF EXISTS tenant_isolation ON properties;
CREATE POLICY tenant_isolation ON properties
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));

-- 3. reservations
-- ENABLE ROW LEVEL SECURITY already present in schema.sql
DROP POLICY IF EXISTS tenant_isolation ON reservations;
CREATE POLICY tenant_isolation ON reservations
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));
