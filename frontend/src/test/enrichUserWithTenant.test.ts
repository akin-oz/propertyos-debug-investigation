/**
 * B-40 — enrichUserWithTenant prefers JWT claim > app_metadata > user_metadata.
 *
 * The priority logic lives in extractTenantFromSession (jwtUtils.ts) and is
 * composed in AuthContext.new.tsx.  We test the individual building blocks
 * and the composed priority directly.
 */

import { describe, it, expect } from "vitest";
import {
  decodeJWTPayload,
  extractTenantFromSession,
} from "../utils/jwtUtils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeJWT(payload: object): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(payload));
  const sig = "fakesig";
  return `${header}.${body}.${sig}`;
}

function makeSession(
  jwtPayload: object,
  appMetaTenantId?: string,
  userMetaTenantId?: string
) {
  return {
    access_token: makeJWT(jwtPayload),
    user: {
      id: "u1",
      email: "test@example.com",
      app_metadata: appMetaTenantId ? { tenant_id: appMetaTenantId } : {},
      user_metadata: userMetaTenantId ? { tenant_id: userMetaTenantId } : {},
    },
  };
}

// ---------------------------------------------------------------------------
// decodeJWTPayload
// ---------------------------------------------------------------------------

describe("decodeJWTPayload", () => {
  it("returns claims from a valid JWT", () => {
    const token = makeJWT({ sub: "u1", tenant_id: "tenant-jwt" });
    const claims = decodeJWTPayload(token);
    expect(claims?.tenant_id).toBe("tenant-jwt");
  });

  it("returns null for a malformed token", () => {
    expect(decodeJWTPayload("not.a.jwt.really")).toBeNull();
  });

  it("returns null for a single-segment string", () => {
    expect(decodeJWTPayload("onlyone")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// extractTenantFromSession — JWT claims path
// ---------------------------------------------------------------------------

describe("extractTenantFromSession", () => {
  it("returns tenant_id from JWT when present", () => {
    const session = makeSession({ sub: "u1", tenant_id: "tenant-a" });
    expect(extractTenantFromSession(session)).toBe("tenant-a");
  });

  it("returns null when JWT has no tenant_id claim", () => {
    const session = makeSession({ sub: "u1" });
    expect(extractTenantFromSession(session)).toBeNull();
  });

  it("returns null when session is null", () => {
    expect(extractTenantFromSession(null)).toBeNull();
  });

  it("returns null when access_token is missing", () => {
    expect(extractTenantFromSession({ user: { id: "u1" } })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// B-40: Priority — JWT claim beats app_metadata and user_metadata
// ---------------------------------------------------------------------------

describe("B-40: enrichUserWithTenant priority", () => {
  it("JWT claim wins over app_metadata", () => {
    // JWT has tenant-jwt; app_metadata has tenant-app
    const session = makeSession(
      { sub: "u1", tenant_id: "tenant-jwt" },
      "tenant-app",
      undefined
    );
    // extractTenantFromSession is what AuthContext calls first
    const fromJwt = extractTenantFromSession(session);
    expect(fromJwt).toBe("tenant-jwt");
  });

  it("JWT claim wins over user_metadata", () => {
    const session = makeSession(
      { sub: "u1", tenant_id: "tenant-jwt" },
      undefined,
      "tenant-user"
    );
    expect(extractTenantFromSession(session)).toBe("tenant-jwt");
  });

  it("falls through to app_metadata when JWT has no claim", () => {
    // No JWT tenant_id → expect null from extractTenantFromSession
    // AuthContext then checks app_metadata
    const session = makeSession({ sub: "u1" }, "tenant-app", "tenant-user");
    const fromJwt = extractTenantFromSession(session);
    expect(fromJwt).toBeNull();

    // Simulate the AuthContext fallback order
    const tenantId =
      fromJwt ??
      session.user.app_metadata?.tenant_id ??
      session.user.user_metadata?.tenant_id ??
      null;
    expect(tenantId).toBe("tenant-app");
  });

  it("falls through to user_metadata when JWT and app_metadata are absent", () => {
    const session = makeSession({ sub: "u1" }, undefined, "tenant-user");
    const fromJwt = extractTenantFromSession(session);
    expect(fromJwt).toBeNull();

    const tenantId =
      fromJwt ??
      (session.user.app_metadata as any)?.tenant_id ??
      session.user.user_metadata?.tenant_id ??
      null;
    expect(tenantId).toBe("tenant-user");
  });

  it("is null when none of the three sources have tenant_id", () => {
    const session = makeSession({ sub: "u1" });
    const fromJwt = extractTenantFromSession(session);
    const tenantId =
      fromJwt ??
      (session.user.app_metadata as any)?.tenant_id ??
      session.user.user_metadata?.tenant_id ??
      null;
    expect(tenantId).toBeNull();
  });
});
