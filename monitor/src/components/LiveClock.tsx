"use client";

import { useEffect, useState } from "react";
import { formatKstTimestamp } from "@/lib/format";

/** Ticks every second in KST, independent of the snapshot polling interval. */
export function LiveClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    // Deferred (not called synchronously in the effect body) so the first
    // paint still matches the server's empty render before hydration.
    const kickoff = setTimeout(() => setNow(new Date()), 0);
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => {
      clearTimeout(kickoff);
      clearInterval(id);
    };
  }, []);

  return <span suppressHydrationWarning>{now ? formatKstTimestamp(now) : ""}</span>;
}
