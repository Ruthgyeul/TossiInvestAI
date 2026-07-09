import { NextResponse } from "next/server";
import { CoreClientError } from "@/lib/core-client";
import { getSnapshot } from "@/lib/get-snapshot";

// Kiosk polls this on an interval — always compute fresh, never cache.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await getSnapshot());
  } catch (err) {
    // MonitorDashboard ignores a non-ok response and keeps the last known-good
    // snapshot on screen (docs/MONITOR.md 절대 규칙 4) — this never blanks the kiosk.
    const message = err instanceof CoreClientError ? err.message : "snapshot unavailable";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
