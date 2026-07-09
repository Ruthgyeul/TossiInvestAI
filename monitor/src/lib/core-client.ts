import "server-only";

/**
 * Server-side only client for core's internal API (docs/INTERNAL_API.md). Never import
 * this from a Client Component — CORE_INTERNAL_API_TOKEN must not reach the browser.
 */

const REQUEST_TIMEOUT_MS = 5000;

export class CoreClientError extends Error {}

export async function fetchCoreMonitorSnapshot(): Promise<Record<string, unknown>> {
  const baseUrl = process.env.CORE_INTERNAL_API_URL;
  const token = process.env.CORE_INTERNAL_API_TOKEN;
  if (!baseUrl || !token) {
    throw new CoreClientError("CORE_INTERNAL_API_URL/CORE_INTERNAL_API_TOKEN is not set");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const res = await fetch(`${baseUrl}/api/v1/monitor/snapshot`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new CoreClientError(`core responded ${res.status}`);
    }
    return (await res.json()) as Record<string, unknown>;
  } catch (err) {
    if (err instanceof CoreClientError) throw err;
    throw new CoreClientError(`core request failed: ${(err as Error).message}`);
  } finally {
    clearTimeout(timeout);
  }
}
