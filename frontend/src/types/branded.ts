/**
 * Branded (nominal) types for security-critical identifiers.
 *
 * TypeScript uses structural typing, which means `string` is assignable to any
 * `string` alias — so `tenant_id: string` and `property_id: string` are
 * interchangeable by default.  Branding adds a phantom field that makes the
 * types nominally distinct:
 *
 *   const tid = asTenantId(user.tenant_id);   // ✅ explicit cast at trust boundary
 *   fetchRevenue(propertyId, tenantId);        // ✅ typed
 *   fetchRevenue(tenantId, propertyId);        // ❌ tsc error — wrong brand
 *   fetchRevenue("raw-string", tenantId);      // ❌ tsc error — unbranded string
 *
 * The brand is erased at runtime — no performance cost.
 */

declare const __brand: unique symbol;

type Brand<T, B extends string> = T & { readonly [__brand]: B };

/**
 * Opaque tenant identifier.  Only create via `asTenantId()`.
 */
export type TenantId = Brand<string, "TenantId">;

/**
 * Opaque property identifier.  Only create via `asPropertyId()`.
 */
export type PropertyId = Brand<string, "PropertyId">;

/**
 * Cast a validated string to TenantId.
 *
 * Call only at the trust boundary — after the value is retrieved from a
 * verified auth token or API response, never from arbitrary user input.
 *
 * @throws {Error} if the value is empty or whitespace-only.
 */
export function asTenantId(value: string): TenantId {
  if (!value || !value.trim()) {
    throw new Error("TenantId must be a non-empty string");
  }
  return value as TenantId;
}

/**
 * Cast a validated string to PropertyId.
 *
 * Call only after the value has been retrieved from the /properties API
 * response, not from raw URL params or user input.
 */
export function asPropertyId(value: string): PropertyId {
  if (!value || !value.trim()) {
    throw new Error("PropertyId must be a non-empty string");
  }
  return value as PropertyId;
}
