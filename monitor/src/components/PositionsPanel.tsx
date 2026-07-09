import type { Position } from "@/lib/types";
import { formatPct, signClass } from "@/lib/format";
import styles from "./Dashboard.module.css";

export function PositionsPanel({ positions }: { positions: Position[] }) {
  return (
    <div className={`${styles.card} ${styles.positionsCard}`}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>KR·US 포지션</div>
        <div className={styles.sectionMeta}>수익률순 · {positions.length}종목</div>
      </div>
      {positions.map((p) => (
        <div className={styles.positionRow} key={`${p.market}-${p.symbol}`}>
          <span className={styles.positionName}>
            <span
              className={`${styles.marketTag} ${p.market === "KR" ? styles.marketTagKr : styles.marketTagUs}`}
            >
              {p.market}
            </span>
            {p.symbol} <span className={styles.positionQty}>{p.quantityLabel}</span>
          </span>
          <span className={`${styles.positionReturn} ${styles[signClass(p.returnPct)]}`}>
            {formatPct(p.returnPct, 1)}
          </span>
        </div>
      ))}
    </div>
  );
}
