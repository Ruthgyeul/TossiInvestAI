import { KioskStage } from "@/components/KioskStage";
import { MonitorDashboard } from "@/components/MonitorDashboard";
import { getSnapshot } from "@/lib/get-snapshot";
import type { MonitorSnapshot } from "@/lib/types";

// Must be re-fetched per request, not baked in at build time — otherwise a
// build run without a reachable core would statically prerender a stale
// ConnectingScreen (or mock data) that never updates in production.
export const dynamic = "force-dynamic";

export default async function Home() {
  let initialSnapshot: MonitorSnapshot | null = null;
  try {
    initialSnapshot = await getSnapshot();
  } catch {
    // core is unreachable on first load — MonitorDashboard shows a connecting
    // screen and retries client-side until a snapshot lands.
  }

  return (
    <KioskStage>
      <MonitorDashboard initialSnapshot={initialSnapshot} />
    </KioskStage>
  );
}
