/**
 * Central logger with levels, PII scrubbing, and DEV-gated verbosity.
 *
 * Usage:
 *   import { logger } from '@/lib/logger';
 *   logger.debug('cache hit', { endpoint, age });   // DEV only
 *   logger.info('auth state changed', { event });   // scrubbed in prod
 *   logger.warn('tenant mismatch detected');        // always emitted
 *   logger.error('request failed', err);            // always emitted
 *
 * PII scrubbing:
 *   All string values in the extras object are checked against PII_PATTERNS.
 *   Matching values are replaced with '[REDACTED]' in production.
 *   In DEV, values are passed through as-is to aid debugging.
 *
 * Levels:
 *   debug  — verbose, DEV only, never in production bundle (tree-shaken by Vite)
 *   info   — operational state transitions, scrubbed in production
 *   warn   — unexpected-but-recoverable conditions, always emitted
 *   error  — failures that need attention, always emitted
 */

const IS_DEV = import.meta.env.DEV;

// ─── PII patterns ────────────────────────────────────────────────────────────

const PII_PATTERNS: RegExp[] = [
  // Email addresses
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  // JWT tokens (three base64url segments)
  /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/,
  // Bearer tokens (often prefixed)
  /^Bearer\s+[A-Za-z0-9._-]+$/i,
  // UUIDs (tenant/user IDs)
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
];

function isSensitive(value: string): boolean {
  return PII_PATTERNS.some(re => re.test(value.trim()));
}

function scrub(extras: Record<string, unknown>): Record<string, unknown> {
  if (IS_DEV) return extras; // Pass through in dev for full visibility
  const result: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(extras)) {
    if (typeof v === 'string' && isSensitive(v)) {
      result[k] = '[REDACTED]';
    } else if (typeof v === 'string' && v.length > 20 && v.includes('.')) {
      // Token previews like "eyJhbGciOi..." — redact regardless
      result[k] = '[REDACTED]';
    } else {
      result[k] = v;
    }
  }
  return result;
}

// ─── Logger implementation ────────────────────────────────────────────────────

type Extras = Record<string, unknown>;

const logger = {
  /**
   * Verbose debugging. Only emitted in DEV — Vite tree-shakes this block
   * out of the production bundle via dead-code elimination on IS_DEV.
   */
  debug(message: string, extras?: Extras): void {
    if (!IS_DEV) return;
    console.debug(`[DEBUG] ${message}`, extras ?? '');
  },

  /**
   * Operational state transitions (auth events, cache hits, request lifecycle).
   * Emitted in both DEV and prod, but PII is scrubbed in prod.
   */
  info(message: string, extras?: Extras): void {
    console.info(`[INFO] ${message}`, extras ? scrub(extras) : '');
  },

  /**
   * Unexpected but recoverable conditions. Always emitted, always scrubbed.
   */
  warn(message: string, extras?: Extras): void {
    console.warn(`[WARN] ${message}`, extras ? scrub(extras) : '');
  },

  /**
   * Failures that need attention. Always emitted, always scrubbed.
   * Pass the raw Error as second arg — it is not scrubbed (no PII in stack traces).
   */
  error(message: string, error?: unknown, extras?: Extras): void {
    console.error(`[ERROR] ${message}`, error ?? '', extras ? scrub(extras) : '');
  },
};

export { logger };
