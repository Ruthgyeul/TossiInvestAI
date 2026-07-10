"use client";

import { useRef } from "react";
import type { SystemHealthSnapshot } from "@/lib/types";
import styles from "./Dashboard.module.css";
import { useFitLogs } from "@/lib/useFitLogs";
import { useVerticalMarqueeFit } from "@/lib/useMarqueeLoop";
import { useRotatingIndex } from "@/lib/useRotatingIndex";

const STATUS_DOT_CLASS = {
  ok: styles.statusOk,
  warn: styles.statusWarn,
  error: styles.statusError,
} as const;

const LOG_LEVEL_CLASS = {
  INFO: styles.logLevelInfo,
  WARN: styles.logLevelWarn,
  ERROR: styles.logLevelError,
} as const;

export function SystemHealthPanel({ data }: { data: SystemHealthSnapshot }) {
  const statusIdx = useRotatingIndex(data.services.length, 5000);
  const service = data.services[statusIdx];
  const logListRef = useRef<HTMLDivElement>(null);
  useFitLogs(logListRef, [data.logs]);
  const selfAssessViewportRef = useRef<HTMLDivElement>(null);
  const selfAssessTextRef = useRef<HTMLSpanElement>(null);
  const selfAssess = useVerticalMarqueeFit(
    selfAssessViewportRef,
    selfAssessTextRef,
    data.selfAssessment.summary,
  );

  return (
    <div className={`${styles.card} ${styles.systemHealthCard}`}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>시스템 상태</div>
        <div className={styles.sectionMetaHealth}>
          에러 {data.errorCountToday}건 · HB {data.lastHeartbeatSecondsAgo}초 전
        </div>
      </div>

      <div className={styles.serviceRotator}>
        <span className={styles.serviceName}>
          <span className={`${styles.statusDot} ${STATUS_DOT_CLASS[service.status]}`} />
          {service.name}
        </span>
        <span className={styles.serviceDetail}>{service.detail}</span>
      </div>

      <div ref={logListRef} className={styles.logList}>
        {data.logs.map((log, i) => (
          <div className={styles.logRow} key={i}>
            <span className={styles.logTime}>{log.time}</span>
            <span className={`${styles.logLevel} ${LOG_LEVEL_CLASS[log.level]}`}>{log.level}</span>
            <span className={styles.logMessage}>{log.message}</span>
          </div>
        ))}
      </div>

      <div className={styles.subsectionHeader}>
        <div className={styles.subsectionTitle}>Safety Gate 거부</div>
        <div className={styles.safetyGateRate}>
          {data.safetyGate.passRateLabel} · 최근 {data.safetyGate.rejections.length}건
        </div>
      </div>
      {data.safetyGate.rejections.map((rej, i) => (
        <div className={styles.safetyRow} key={i}>
          <span className={styles.safetyTime}>{rej.time}</span>
          <span className={styles.safetyText}>{rej.message}</span>
        </div>
      ))}

      <div className={styles.selfAssessBlock}>
        <div className={styles.selfAssessHeader}>
          <span className={styles.subsectionTitle}>자기평가</span>
          <span className={styles.selfAssessTime}>{data.selfAssessment.time}</span>
        </div>
        <div className={styles.selfAssessViewport} ref={selfAssessViewportRef}>
          <div className={styles.marqueeTrackVertical} style={{ animation: selfAssess.animation }}>
            <span
              className={styles.selfAssessSummary}
              ref={selfAssessTextRef}
              style={{ paddingBottom: selfAssess.gap }}
            >
              {data.selfAssessment.summary}
            </span>
            {selfAssess.overflowing && (
              <span className={styles.selfAssessSummary} style={{ paddingBottom: selfAssess.gap }}>
                {data.selfAssessment.summary}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
