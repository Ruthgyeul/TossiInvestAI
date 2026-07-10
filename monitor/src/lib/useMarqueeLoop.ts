"use client";

import { useEffect, useState } from "react";

interface MarqueeFit {
  overflowing: boolean;
  gap: number;
  animation: string;
}

/**
 * Fit-checking for the CSS keyframe "double the content, loop -50%" marquee technique
 * (source design's `bin-report-marquee`/`bin-report-marquee-y` + `fitHorizontalMarquee`/
 * `fitVerticalMarquee`). Used for content that doesn't rotate on its own (report summary,
 * self-assessment) or rotates on a fixed timer (market event) — re-measures whenever
 * `text` changes so a newly-rotated-in item gets its own overflow/duration check.
 *
 * Takes the viewport/content refs as arguments (rather than creating and returning them)
 * so callers own their own `useRef` — keeping refs and derived render values in separate
 * hook results avoids the "accessing ref during render" footgun on a single mixed object.
 */
function useMarqueeFit(
  measure: (viewport: HTMLElement, content: HTMLElement) => number,
  viewportRef: React.RefObject<HTMLElement | null>,
  contentRef: React.RefObject<HTMLElement | null>,
  text: string,
  minDuration: number,
  pxPerSec: number,
  animationName: string,
  gap: number,
): MarqueeFit {
  const [state, setState] = useState({ overflowing: false, duration: minDuration });

  useEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return;

    const recompute = () => {
      const size = measure(viewport, content);
      const overflowing = size > 0;
      const duration = Math.max(minDuration, Math.abs(size) / pxPerSec);
      setState((s) => (s.overflowing === overflowing && s.duration === duration ? s : { overflowing, duration }));
    };

    recompute();
    window.addEventListener("resize", recompute);
    document.fonts?.ready?.then(recompute);
    return () => window.removeEventListener("resize", recompute);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  return {
    overflowing: state.overflowing,
    gap: state.overflowing ? gap : 0,
    animation: state.overflowing ? `${animationName} ${state.duration}s linear infinite` : "none",
  };
}

export function useHorizontalMarqueeFit(
  viewportRef: React.RefObject<HTMLElement | null>,
  textRef: React.RefObject<HTMLElement | null>,
  text: string,
  gap = 40,
): MarqueeFit {
  return useMarqueeFit(
    (viewport, content) => content.offsetWidth - viewport.clientWidth,
    viewportRef,
    textRef,
    text,
    6,
    60,
    "bin-marquee-x",
    gap,
  );
}

export function useVerticalMarqueeFit(
  viewportRef: React.RefObject<HTMLElement | null>,
  textRef: React.RefObject<HTMLElement | null>,
  text: string,
  gap = 14,
): MarqueeFit {
  return useMarqueeFit(
    (viewport, content) => content.offsetHeight - viewport.clientHeight,
    viewportRef,
    textRef,
    text,
    5,
    20,
    "bin-marquee-y",
    gap,
  );
}
