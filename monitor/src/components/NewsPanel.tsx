"use client";

import { useCallback, useRef, useState } from "react";
import type { NewsHeadline } from "@/lib/types";
import styles from "./Dashboard.module.css";
import { useTickerScroll } from "@/lib/useTickerScroll";

const SENTIMENT_CLASS = {
  호재: styles.sentimentGood,
  주의: styles.sentimentCaution,
  악재: styles.sentimentBad,
} as const;

export function NewsPanel({ news }: { news: NewsHeadline[] }) {
  const [index, setIndex] = useState(0);
  const boundedIndex = news.length > 0 ? index % news.length : 0;
  const item = news[boundedIndex];

  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);

  const advance = useCallback(() => {
    setIndex((i) => (news.length > 0 ? (i + 1) % news.length : 0));
  }, [news.length]);

  useTickerScroll(viewportRef, trackRef, textRef, boundedIndex, { onDone: advance });

  return (
    <div className={`${styles.card} ${styles.panelCard}`}>
      <div className={styles.panelTitle}>뉴스 헤드라인</div>
      <div className={styles.panelDivider} />
      {item && (
        <>
          <div className={styles.newsContent}>
            <span className={`${styles.sentimentBadge} ${SENTIMENT_CLASS[item.sentiment]}`}>
              {item.sentiment}
            </span>
            <div className={styles.tickerViewport} ref={viewportRef}>
              <div className={styles.tickerTrack} ref={trackRef}>
                <span className={styles.newsText} ref={textRef}>
                  {item.text}
                </span>
              </div>
            </div>
          </div>
          <div className={styles.tickerCounter}>
            {boundedIndex + 1}/{news.length}
          </div>
        </>
      )}
    </div>
  );
}
