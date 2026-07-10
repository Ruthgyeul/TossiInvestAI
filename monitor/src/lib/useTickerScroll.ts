"use client";

import { useEffect, useRef } from "react";

interface TickerScrollOptions {
  /** Delay before the scroll starts, so a freshly-rotated-in item is readable at rest first. */
  startDelayMs?: number;
  /** Pause once fully scrolled, before `onDone` fires. */
  holdMs?: number;
  pxPerSec?: number;
  /** Caps the scroll duration to fit inside a fixed rotation interval (perf/risk cards). Omit for news, which paces its own rotation off `onDone`. */
  budgetMs?: number;
  /** Called once the hold period ends — perf/risk ignore it (an external timer drives rotation); news uses it to advance to the next headline. */
  onDone?: () => void;
}

/**
 * Imperative rAF-driven "reveal the tail, then pause" scroll — mirrors the source design's
 * `runScrollEngine`. Deliberately not a CSS animation: restarting an identical
 * `animation-duration` between items can fail to replay in some engines, which the
 * source design's comment calls out explicitly.
 */
export function useTickerScroll(
  viewportRef: React.RefObject<HTMLDivElement | null>,
  trackRef: React.RefObject<HTMLDivElement | null>,
  textRef: React.RefObject<HTMLSpanElement | null>,
  restartKey: unknown,
  options: TickerScrollOptions = {},
): void {
  const { startDelayMs = 1000, holdMs = 900, pxPerSec = 55, budgetMs, onDone } = options;
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const track = trackRef.current;
    const text = textRef.current;
    let raf = 0;
    let advanceTimer: ReturnType<typeof setTimeout> | undefined;

    if (!viewport || !track || !text) {
      return;
    }

    track.style.transform = "translateX(0)";
    const distance = text.offsetWidth - viewport.clientWidth;
    if (distance <= 0) {
      if (onDoneRef.current) advanceTimer = setTimeout(() => onDoneRef.current?.(), 5000);
      return () => clearTimeout(advanceTimer);
    }

    let scrollMs = Math.max(2500, (distance / pxPerSec) * 1000);
    if (budgetMs) scrollMs = Math.min(scrollMs, Math.max(800, budgetMs - startDelayMs - holdMs));

    const startTimer = setTimeout(() => {
      const startTime = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - startTime) / scrollMs);
        track.style.transform = `translateX(-${distance * t}px)`;
        if (t < 1) {
          raf = requestAnimationFrame(step);
        } else if (onDoneRef.current) {
          advanceTimer = setTimeout(() => onDoneRef.current?.(), holdMs);
        }
      };
      raf = requestAnimationFrame(step);
    }, startDelayMs);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(startTimer);
      clearTimeout(advanceTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restartKey, startDelayMs, holdMs, pxPerSec, budgetMs]);
}
