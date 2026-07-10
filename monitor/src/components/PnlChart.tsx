"use client";

import type { PnlChartSnapshot } from "@/lib/types";
import { barHeights, formatSignedKrw } from "@/lib/format";
import { buildChartSeries } from "@/lib/chart-series";
import { useRotatingIndex } from "@/lib/useRotatingIndex";
import styles from "./Dashboard.module.css";

export function PnlChart({ data }: { data: PnlChartSnapshot }) {
  const periodIdx = useRotatingIndex(data.periods.length, 5000);
  const period = data.periods[periodIdx];
  const maxAbs = Math.max(...period.bars.map((value) => Math.abs(value)), 1);
  const series = buildChartSeries(period.bars, period.benchmarkBars);

  return (
    <div className={`${styles.card} ${styles.chartCard}`}>
      <div className={styles.sectionHeader}>
        <div className={styles.chartTitleRow}>
          <div className={styles.chartTitle}>손익 · {period.label}</div>
          <div className={styles.chartLegend}>
            <span className={styles.chartLegendItem}>
              <span className={styles.chartLegendSwatchLine} />
              누적
            </span>
            <span className={styles.chartLegendItem}>
              <span className={styles.chartLegendSwatchDash} />
              벤치마크
            </span>
            <span className={styles.chartLegendItem}>
              <span className={styles.chartLegendSwatchArea} />
              낙폭
            </span>
          </div>
        </div>
        <div className={styles.sectionMetaChart}>
          평균 {period.avgDailyReturnPct >= 0 ? "+" : ""}
          {period.avgDailyReturnPct.toFixed(2)}%/일 · 승률 {period.winRatePct}%
        </div>
      </div>
      <div className={styles.chartBarsWrap}>
        <svg
          className={styles.chartSvgOverlay}
          viewBox="0 0 1000 100"
          preserveAspectRatio="none"
        >
          <path d={series.ddPath} fill="oklch(60% 0.17 30 / 0.16)" stroke="none" />
          {series.benchPath && (
            <path
              d={series.benchPath}
              stroke="oklch(65% 0.14 250)"
              strokeWidth={1.4}
              strokeDasharray="5,4"
              fill="none"
              vectorEffect="non-scaling-stroke"
            />
          )}
          <path
            d={series.cumPath}
            stroke="oklch(88% 0.015 260)"
            strokeWidth={1.8}
            fill="none"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {period.bars.map((value, i) => {
          const { pos, neg } = barHeights(value, maxAbs);
          return (
            <div className={styles.chartBarCol} key={i}>
              <div className={styles.chartBarBody}>
                <div className={styles.chartBarUpWrap}>
                  <div className={styles.chartBarUp} style={{ height: `${pos}%` }} />
                </div>
                <div className={styles.chartBaseline} />
                <div className={styles.chartBarDownWrap}>
                  <div className={styles.chartBarDown} style={{ height: `${neg}%` }} />
                </div>
              </div>
              <div className={styles.chartBarLabel}>{period.xLabels[i]}</div>
            </div>
          );
        })}
      </div>
      <div className={styles.chartFooter}>
        <span className={styles.chartFooterLeft}>
          <span className={`${styles.chartTotal} ${styles.positive}`}>
            ▲ {formatSignedKrw(data.totalUpKrw)}{" "}
            <span className={styles.chartDaysLabel}>상승 {data.upDays}일</span>
          </span>
          <span className={`${styles.chartTotal} ${styles.negative}`}>
            ▼ {formatSignedKrw(data.totalDownKrw)}{" "}
            <span className={styles.chartDaysLabel}>하락 {data.downDays}일</span>
          </span>
        </span>
        <span className={styles.chartNet}>순손익 {formatSignedKrw(data.netKrw)}</span>
      </div>
    </div>
  );
}
