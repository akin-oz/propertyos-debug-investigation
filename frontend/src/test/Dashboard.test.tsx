/**
 * B-12 — Dashboard only shows properties returned by /api/v1/properties.
 *
 * The component calls SecureAPI.getProperties() and maps the result to
 * <option> elements in a <select>.  This test confirms:
 *   - Only the API-returned properties appear (no hard-coded extras).
 *   - Cross-tenant properties (not in the response) are absent.
 *   - An empty response renders a "Loading…" placeholder, not stale data.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Dashboard from "../components/Dashboard";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../lib/secureApi", () => ({
  SecureAPI: {
    getProperties: vi.fn(),
    getDashboardSummary: vi.fn().mockResolvedValue(null),
  },
}));

vi.mock("../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
    from: vi.fn(),
  },
}));

vi.mock("../lib/logger", () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

// RevenueSummary makes its own API call; stub it out to keep Dashboard tests focused
vi.mock("../components/RevenueSummary", () => ({
  RevenueSummary: ({ propertyId }: { propertyId: string }) => (
    <div data-testid="revenue-summary">{propertyId}</div>
  ),
}));

import { SecureAPI } from "../lib/secureApi";
const mockGetProperties = SecureAPI.getProperties as ReturnType<typeof vi.fn>;

describe("B-12: Dashboard property list isolation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders only the properties returned by the API", async () => {
    mockGetProperties.mockResolvedValue({
      data: [
        { id: "prop-001", name: "Beach House" },
        { id: "prop-002", name: "City Apartment" },
      ],
      total: 2,
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("Beach House")).toBeTruthy();
      expect(screen.getByText("City Apartment")).toBeTruthy();
    });

    // No third property should appear
    expect(screen.queryByText("Lakeside Cottage")).toBeNull();
  });

  it("does not show properties from another tenant", async () => {
    // Only tenant-a's property is returned — tenant-b's 'Lakeside Cottage' is absent
    mockGetProperties.mockResolvedValue({
      data: [{ id: "prop-001", name: "Beach House" }],
      total: 1,
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("Beach House")).toBeTruthy();
    });

    expect(screen.queryByText("Lakeside Cottage")).toBeNull();
    expect(screen.queryByText("prop-004")).toBeNull();
  });

  it("shows 'Loading...' placeholder when API returns empty list", async () => {
    mockGetProperties.mockResolvedValue({ data: [], total: 0 });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("Loading...")).toBeTruthy();
    });
  });

  it("calls SecureAPI.getProperties exactly once on mount", async () => {
    mockGetProperties.mockResolvedValue({ data: [], total: 0 });

    render(<Dashboard />);

    await waitFor(() => expect(mockGetProperties).toHaveBeenCalledOnce());
  });

  it("selects the first property by default", async () => {
    mockGetProperties.mockResolvedValue({
      data: [
        { id: "prop-001", name: "Beach House" },
        { id: "prop-002", name: "City Apartment" },
      ],
      total: 2,
    });

    render(<Dashboard />);

    await waitFor(() => {
      const select = screen.getByRole("combobox") as HTMLSelectElement;
      expect(select.value).toBe("prop-001");
    });
  });
});
