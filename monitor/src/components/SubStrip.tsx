"use client";

import { useRef } from "react";
import type { Stat, SubStripSnapshot } from "@/lib/types";
import styles from "./Dashboard.module.css";
import { useHorizontalMarqueeFit } from "@/lib/useMarqueeLoop";
import { useRotatingIndex } from "@/lib/useRotatingIndex";
import { useTickerScroll } from "@/lib/useTickerScroll";

const TONE_CLASS: Record<Stat["tone"], string> = {
  positive: styles.positive,
  negative: styles.negative,
  neutral: styles.neutral,
  good: styles.toneGood,
  warn: styles.toneWarn,
  bad: styles.toneBad,
};

function RotatingStat({ label, stats }: { label: string; stats: Stat[] }) {
  const index = useRotatingIndex(stats.length, 5000);
  const item = stats[index];
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  useTickerScroll(viewportRef, trackRef, textRef, index, {
    budgetMs: 5000,
    startDelayMs: 800,
    holdMs: 400,
  });

  return (
    <>
      <span className={styles.subStripLabel}>{label}</span>
      {item && (
        <div className={styles.tickerViewport} ref={viewportRef}>
          <div className={styles.tickerTrack} ref={trackRef}>
            <span className={`${styles.tickerText} ${TONE_CLASS[item.tone]}`} ref={textRef}>
              {item.label} {item.value}
            </span>
          </div>
        </div>
      )}
    </>
  );
}

export function SubStrip({ data }: { data: SubStripSnapshot }) {
  const reportText = `${data.reportTime} 정기 · ${data.reportSummary}`;
  const reportViewportRef = useRef<HTMLDivElement>(null);
  const reportTextRef = useRef<HTMLSpanElement>(null);
  const report = useHorizontalMarqueeFit(reportViewportRef, reportTextRef, reportText);

  return (
    <div className={styles.subStrip}>
      <div className={styles.subStripPerf}>
        <RotatingStat label="성과" stats={data.perfStats} />
      </div>
      <div className={styles.subStripRisk}>
        <RotatingStat label="리스크" stats={data.riskStats} />
      </div>
      <div className={styles.subStripFng}>
        <span className={styles.subStripLabel}>공포탐욕지수</span>
        <span className={styles.fngValue}>
          {data.fearGreedIndex ?? "-"} {data.fearGreedLabel}
        </span>
      </div>
      <div className={styles.subStripReport}>
        <span className={styles.subStripLabel}>리포트</span>
        <div className={styles.marqueeViewport} ref={reportViewportRef}>
          <div className={styles.marqueeTrack} style={{ animation: report.animation }}>
            <span
              className={styles.marqueeText}
              ref={reportTextRef}
              style={{ paddingRight: report.gap }}
            >
              {reportText}
            </span>
            {report.overflowing && (
              <span className={styles.marqueeText} style={{ paddingRight: report.gap }}>
                {reportText}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
