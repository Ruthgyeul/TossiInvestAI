import type { SubStripSnapshot } from "@/lib/types";
import styles from "./Dashboard.module.css";

export function SubStrip({ data }: { data: SubStripSnapshot }) {
  return (
    <div className={styles.subStrip}>
      <div className={styles.subStripReport}>
        <span className={styles.subStripLabel}>리포트</span>
        <span className={styles.subStripValue}>
          {data.reportTime} 정기 · {data.reportSummary}
        </span>
      </div>
      <div className={styles.subStripSelfImprove}>
        <span className={styles.subStripLabel}>자기개선</span>
        <span className={styles.pendingBadge}>
          승인대기 {data.selfImprovementPendingCount}건 · {data.selfImprovementVersion}
        </span>
      </div>
      <div className={styles.subStripToss}>
        <span className={styles.subStripLabel}>토스 인기 겹침</span>
        <span className={styles.subStripValue}>
          {data.tossOverlapSymbols.join(" · ")}{" "}
          <span className={styles.subStripMuted}>
            (보유 {data.tossOverlapHoldingCount}/{data.tossOverlapTotalCount})
          </span>
        </span>
      </div>
      <div className={styles.subStripFng}>
        <span className={styles.subStripLabel}>공포탐욕지수</span>
        <span className={styles.fngValue}>
          {data.fearGreedIndex ?? "-"} {data.fearGreedLabel}
        </span>
      </div>
    </div>
  );
}
