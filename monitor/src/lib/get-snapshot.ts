import "server-only";

import { fetchCoreMonitorSnapshot } from "./core-client";
import { getMockSnapshot } from "./mock-snapshot";
import { mapCoreSnapshot } from "./snapshot-mapper";
import type { MonitorSnapshot } from "./types";

/**
 * Single source of truth for both `/api/snapshot` (polled every 30s by
 * MonitorDashboard) and the initial server-rendered page — avoids the
 * page doing a self-HTTP-call to its own route handler. Throws
 * CoreClientError on failure; callers decide how to degrade
 * (docs/MONITOR.md 절대 규칙 4 — 폴링 실패가 화면을 비우면 안 된다).
 */
export async function getSnapshot(): Promise<MonitorSnapshot> {
  if (process.env.MONITOR_USE_MOCK_DATA === "true") {
    return getMockSnapshot();
  }
  const raw = await fetchCoreMonitorSnapshot();
  return mapCoreSnapshot(raw);
}
