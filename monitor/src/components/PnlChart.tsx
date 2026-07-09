import type { PnlChartSnapshot } from "@/lib/types";
import { barHeights, formatSignedKrw } from "@/lib/format";
import styles from "./Dashboard.module.css";

export function PnlChart({ data }: { data: PnlChartSnapshot }) {
  return (
    <div className={`${styles.card} ${styles.chartCard}`}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>일별 손익 · {data.periodLabel}</div>
        <div className={styles.sectionMeta}>
          평균 {data.avgDailyReturnPct >= 0 ? "+" : ""}
          {data.avgDailyReturnPct.toFixed(2)}%/일 · 승률 {data.winRatePct}%
        </div>
      </div>
      <div className={styles.chartBars}>
        {(() => {
          const maxAbs = Math.max(...data.bars.map((value) => Math.abs(value)), 1);
          return data.bars.map((value, i) => {
            const { pos, neg } = barHeights(value, maxAbs);
            return (
              <div className={styles.chartBarCol} key={i}>
                <div className={styles.chartBarUpWrap}>
                  <div className={styles.chartBarUp} style={{ height: `${pos}%` }} />
                </div>
                <div className={styles.chartBaseline} />
                <div className={styles.chartBarDownWrap}>
                  <div className={styles.chartBarDown} style={{ height: `${neg}%` }} />
                </div>
              </div>
            );
          });
        })()}
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
