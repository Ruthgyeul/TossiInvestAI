import type { NewsHeadline } from "@/lib/types";
import styles from "./Dashboard.module.css";

const SENTIMENT_CLASS = {
  호재: styles.sentimentGood,
  주의: styles.sentimentCaution,
  악재: styles.sentimentBad,
} as const;

export function NewsPanel({ news }: { news: NewsHeadline[] }) {
  return (
    <div className={`${styles.card} ${styles.panelCard}`}>
      <div className={styles.panelTitle}>뉴스 헤드라인</div>
      {news.map((item, i) => (
        <div className={styles.newsRow} key={i}>
          <span className={`${styles.sentimentBadge} ${SENTIMENT_CLASS[item.sentiment]}`}>
            {item.sentiment}
          </span>
          <span className={styles.newsText}>{item.text}</span>
        </div>
      ))}
    </div>
  );
}
