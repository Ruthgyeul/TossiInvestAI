"use client";

import { useEffect } from "react";

/**
 * Hides trailing log rows that would overflow the fixed-height list — mirrors the source
 * design's `fitLogs()`. Rows have variable height (a single long entry can wrap to several
 * lines), so this measures actual rendered heights rather than assuming a fixed row count.
 */
export function useFitLogs(listRef: React.RefObject<HTMLDivElement | null>, deps: readonly unknown[]): void {
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;

    const fit = () => {
      const maxHeight = el.clientHeight;
      const children = Array.from(el.children) as HTMLElement[];
      children.forEach((c) => {
        c.style.display = "flex";
      });
      let cumulative = 0;
      let overflowAt = -1;
      children.forEach((child, i) => {
        cumulative += child.offsetHeight + (i > 0 ? 1 : 0);
        if (overflowAt === -1 && cumulative > maxHeight) overflowAt = i;
      });
      if (overflowAt >= 0) {
        for (let i = overflowAt; i < children.length; i++) children[i].style.display = "none";
      }
    };

    fit();
    window.addEventListener("resize", fit);
    document.fonts?.ready?.then(fit);
    return () => window.removeEventListener("resize", fit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
