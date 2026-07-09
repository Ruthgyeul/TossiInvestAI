import type { HeaderSnapshot } from "@/lib/types";
import styles from "./Dashboard.module.css";
import { LiveClock } from "./LiveClock";

export function Header({ data }: { data: HeaderSnapshot }) {
  return (
    <div className={styles.header}>
      <div className={styles.headerLeft}>
        <div className={styles.logo}>빈</div>
        <div className={styles.title}>BIN MONITOR</div>
        <div className={styles.liveBadge}>
          <span className={styles.liveDot} />
          <span className={styles.liveText}>LIVE</span>
        </div>
        <div className={styles.versionTag}>
          strategy {data.strategyVersion} · prompt {data.promptVersion}
        </div>
      </div>
      <div className={styles.headerRight}>
        <span>USD/KRW {data.usdKrw.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span>
          KR {data.krMarketStatus} · US {data.usMarketStatus}
        </span>
        <LiveClock />
      </div>
    </div>
  );
}
