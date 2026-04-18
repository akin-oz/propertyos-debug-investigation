/**
 * B-37 — RevenueSummary renders loading / error / success / precision-mismatch states.
 */

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RevenueSummary } from "../components/RevenueSummary";

// ---------------------------------------------------------------------------
// Mock SecureAPI singleton so we never hit the network
// ---------------------------------------------------------------------------

vi.mock("../lib/secureApi", () => ({
  SecureAPI: {
    getDashboardSummary: vi.fn(),
  },
}));

// Also mock supabase (imported transitively by secureApi)
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

// Mock logger to suppress output in tests
vi.mock("../lib/logger", () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { SecureAPI } from "../lib/secureApi";
const mockGetSummary = SecureAPI.getDashboardSummary as ReturnType<typeof vi.fn>;

describe("RevenueSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("renders loading skeleton while request is in flight", async () => {
    // Never resolves during the test
    mockGetSummary.mockReturnValue(new Promise(() => {}));

    render(<RevenueSummary propertyId="prop-001" />);

    // The skeleton uses animate-pulse; check the wrapper div exists
    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).not.toBeNull();
  });

  it("renders nothing (null) when propertyId is absent", async () => {
    const { container } = render(<RevenueSummary />);
    // After the effect settles: loading=false, data=null → null returned
    await waitFor(() => {
      expect(document.querySelector(".animate-pulse")).toBeNull();
    });
    // Component returns null — container children may be empty
    expect(screen.queryByText("Revenue data unavailable")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("renders error message when API call rejects", async () => {
    mockGetSummary.mockRejectedValue(new Error("Network error"));

    render(<RevenueSummary propertyId="prop-001" />);

    await waitFor(() => {
      expect(screen.getByText("Revenue data unavailable")).toBeTruthy();
    });
  });

  it("retry button increments retryCount and re-fetches", async () => {
    mockGetSummary
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValueOnce({
        property_id: "prop-001",
        total_revenue: "100.00",
        currency: "USD",
        reservations_count: 2,
      });

    render(<RevenueSummary propertyId="prop-001" />);

    await waitFor(() =>
      expect(screen.getByText("Revenue data unavailable")).toBeTruthy()
    );

    const retryBtn = screen.getByText("Try again");
    await userEvent.click(retryBtn);

    await waitFor(() =>
      expect(screen.getByText(/Total Revenue/i)).toBeTruthy()
    );

    expect(mockGetSummary).toHaveBeenCalledTimes(2);
  });

  // -------------------------------------------------------------------------
  // Success state
  // -------------------------------------------------------------------------

  it("renders revenue, currency, and reservation count on success", async () => {
    mockGetSummary.mockResolvedValue({
      property_id: "prop-001",
      total_revenue: "1234.56",
      currency: "USD",
      reservations_count: 7,
    });

    render(<RevenueSummary propertyId="prop-001" />);

    await waitFor(() => {
      expect(screen.getByText(/1,234.56|1234.56/)).toBeTruthy();
    });

    expect(screen.getByText("USD 1,234.56")).toBeTruthy();
    expect(screen.getByText(/7/)).toBeTruthy();
    expect(screen.getByText("prop-001")).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // Precision-mismatch state
  // -------------------------------------------------------------------------

  it("shows precision mismatch warning when total_revenue has sub-cent drift", async () => {
    // "1000.001" → parsed = 1000.001; rounded = 1000.00; diff = 0.001 > 0.000001
    mockGetSummary.mockResolvedValue({
      property_id: "prop-001",
      total_revenue: "1000.001",
      currency: "USD",
      reservations_count: 3,
    });

    render(<RevenueSummary propertyId="prop-001" />);

    await waitFor(() => {
      expect(screen.getByText("Precision Mismatch Detected")).toBeTruthy();
    });
  });

  it("does NOT show precision mismatch when total_revenue is exact", async () => {
    mockGetSummary.mockResolvedValue({
      property_id: "prop-001",
      total_revenue: "1000.00",
      currency: "USD",
      reservations_count: 3,
    });

    render(<RevenueSummary propertyId="prop-001" />);

    await waitFor(() => {
      expect(screen.getByText(/1,000.00|1000.00/)).toBeTruthy();
    });

    expect(screen.queryByText("Precision Mismatch Detected")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // showRaw prop
  // -------------------------------------------------------------------------

  it("shows raw API response when showRaw=true", async () => {
    const payload = {
      property_id: "prop-001",
      total_revenue: "50.00",
      currency: "EUR",
      reservations_count: 1,
    };
    mockGetSummary.mockResolvedValue(payload);

    render(<RevenueSummary propertyId="prop-001" showRaw />);

    await waitFor(() => {
      expect(screen.getByText("Raw API Response")).toBeTruthy();
    });
  });
});
