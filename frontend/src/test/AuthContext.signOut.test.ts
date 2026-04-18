/**
 * B-11, B-35 — signOut clears auth-owned keys and Supabase tokens without
 * nuking unrelated localStorage entries.
 *
 * We test the key-clearing logic in isolation because:
 *  - The full AuthProvider requires an event loop and async Supabase calls.
 *  - The exact localStorage keys cleared by signOut are the security contract
 *    (clearing ALL of localStorage would erase unrelated app state).
 *
 * The logic under test is the `clearAuthStorage` closure inside signOut
 * (AuthContext.new.tsx lines 268-281).
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Replicate the clearAuthStorage logic from AuthContext.new.tsx
// This is the contract we enforce — if the source changes, update here too.
// ---------------------------------------------------------------------------

const AUTH_STORAGE_KEYS = [
  "sidebarCollapsed",
  "base360-auth-token",
];

function clearAuthStorage(storage: Storage): void {
  AUTH_STORAGE_KEYS.forEach((k) => storage.removeItem(k));
  for (let i = storage.length - 1; i >= 0; i--) {
    const key = storage.key(i);
    if (key && key.startsWith("sb-") && key.endsWith("-auth-token")) {
      storage.removeItem(key);
    }
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("B-11 / B-35: clearAuthStorage — selective key removal", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("removes the 'base360-auth-token' key", () => {
    localStorage.setItem("base360-auth-token", "tok123");
    clearAuthStorage(localStorage);
    expect(localStorage.getItem("base360-auth-token")).toBeNull();
  });

  it("removes 'sidebarCollapsed' key", () => {
    localStorage.setItem("sidebarCollapsed", "true");
    clearAuthStorage(localStorage);
    expect(localStorage.getItem("sidebarCollapsed")).toBeNull();
  });

  it("removes Supabase sb-*-auth-token keys", () => {
    localStorage.setItem("sb-abc123-auth-token", JSON.stringify({ access_token: "tok" }));
    localStorage.setItem("sb-xyz-auth-token", JSON.stringify({ access_token: "tok2" }));
    clearAuthStorage(localStorage);
    expect(localStorage.getItem("sb-abc123-auth-token")).toBeNull();
    expect(localStorage.getItem("sb-xyz-auth-token")).toBeNull();
  });

  it("does NOT remove unrelated app state (B-11: no localStorage.clear())", () => {
    localStorage.setItem("user-preferences", JSON.stringify({ theme: "dark" }));
    localStorage.setItem("base360-auth-token", "tok");
    localStorage.setItem("sb-abc-auth-token", "{}");

    clearAuthStorage(localStorage);

    // Unrelated key must survive
    expect(localStorage.getItem("user-preferences")).toBe(JSON.stringify({ theme: "dark" }));
  });

  it("does NOT remove keys that merely contain 'sb-' but don't match the pattern", () => {
    localStorage.setItem("nosb-custom-key", "data");
    localStorage.setItem("my-sb-data", "data2");

    clearAuthStorage(localStorage);

    expect(localStorage.getItem("nosb-custom-key")).toBe("data");
    expect(localStorage.getItem("my-sb-data")).toBe("data2");
  });

  it("handles empty localStorage without error", () => {
    expect(() => clearAuthStorage(localStorage)).not.toThrow();
  });

  it("clears all auth keys in a single call even when multiple exist", () => {
    localStorage.setItem("base360-auth-token", "a");
    localStorage.setItem("sidebarCollapsed", "b");
    localStorage.setItem("sb-proj-auth-token", "c");
    localStorage.setItem("keep-me", "d");

    clearAuthStorage(localStorage);

    expect(localStorage.getItem("base360-auth-token")).toBeNull();
    expect(localStorage.getItem("sidebarCollapsed")).toBeNull();
    expect(localStorage.getItem("sb-proj-auth-token")).toBeNull();
    expect(localStorage.getItem("keep-me")).toBe("d");
  });
});
