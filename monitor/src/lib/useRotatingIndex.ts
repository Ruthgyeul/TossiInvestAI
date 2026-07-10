"use client";

import { useEffect, useState } from "react";

/** Cycles through `[0, length)` every `intervalMs` — drives the sub-strip/chart/system-health rotators. */
export function useRotatingIndex(length: number, intervalMs: number): number {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (length <= 1) return;
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % length);
    }, intervalMs);
    return () => clearInterval(id);
  }, [length, intervalMs]);

  return length > 0 ? index % length : 0;
}
