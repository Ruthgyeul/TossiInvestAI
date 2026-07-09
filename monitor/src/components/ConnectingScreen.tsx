import styles from "./ConnectingScreen.module.css";

/**
 * Shown only on the very first server render when core has never returned a
 * snapshot yet — there is no "last known-good" snapshot to fall back on
 * (unlike MonitorDashboard's polling failures, docs/MONITOR.md 절대 규칙 4).
 * No interactive elements, matching the dashboard's read-only kiosk rule.
 */
export function ConnectingScreen() {
  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <span className={styles.dot} />
        <span className={styles.title}>core 연결 대기 중</span>
        <span className={styles.detail}>/api/v1/monitor/snapshot 응답 없음 · 재시도 중</span>
      </div>
    </div>
  );
}
