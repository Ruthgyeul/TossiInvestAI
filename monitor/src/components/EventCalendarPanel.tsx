import type { MarketEvent } from "@/lib/types";
import styles from "./Dashboard.module.css";

export function EventCalendarPanel({ events }: { events: MarketEvent[] }) {
  return (
    <div className={`${styles.card} ${styles.panelCard}`}>
      <div className={styles.panelTitle}>시장 이벤트 캘린더</div>
      {events.map((event, i) => (
        <div className={styles.eventRow} key={i}>
          <span>{event.label}</span>
          {event.risk === "고위험" ? (
            <span className={styles.riskBadge}>고위험</span>
          ) : (
            <span className={styles.daysLabel}>{event.daysUntilLabel}</span>
          )}
        </div>
      ))}
    </div>
  );
}
