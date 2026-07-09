import type { AiDecision } from "@/lib/types";
import styles from "./Dashboard.module.css";

const BADGE_CLASS = {
  BUY: styles.decisionBadgeBuy,
  SELL: styles.decisionBadgeSell,
  HOLD: styles.decisionBadgeHold,
} as const;

export function AiDecisionsPanel({
  decisions,
  countToday,
}: {
  decisions: AiDecision[];
  countToday: number;
}) {
  return (
    <div className={`${styles.card} ${styles.aiDecisionsCard}`}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>AI 매매 판단</div>
        <div className={styles.sectionMeta}>금일 {countToday}건</div>
      </div>
      {decisions.map((d, i) => (
        <div className={styles.decisionRow} key={i}>
          <span className={styles.decisionTime}>{d.time}</span>
          <span className={`${styles.decisionBadge} ${BADGE_CLASS[d.action]}`}>{d.action}</span>
          <span className={styles.decisionSymbol}>{d.symbol}</span>
          <span className={styles.decisionConfidence}>{d.confidencePct}%</span>
        </div>
      ))}
    </div>
  );
}
