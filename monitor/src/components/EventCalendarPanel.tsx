"use client";

import type { MarketEvent } from "@/lib/types";
import styles from "./Dashboard.module.css";
import { useRotatingIndex } from "@/lib/useRotatingIndex";

export function EventCalendarPanel({ events }: { events: MarketEvent[] }) {
  const index = useRotatingIndex(events.length, 5000);
  const event = events[index];

  return (
    <div className={`${styles.card} ${styles.panelCard}`}>
      <div className={styles.panelTitle}>시장 이벤트</div>
      <div className={styles.panelDivider} />
      {event && (
        <>
          <div className={styles.eventContent}>
            <span className={styles.eventText}>{event.label}</span>
            {event.risk === "고위험" ? (
              <span className={`${styles.eventTag} ${styles.eventTagRisk}`}>고위험</span>
            ) : (
              <span className={`${styles.eventTag} ${styles.eventTagNeutral}`}>{event.daysUntilLabel}</span>
            )}
          </div>
          <div className={styles.tickerCounter}>
            {index + 1}/{events.length}
          </div>
        </>
      )}
    </div>
  );
}
