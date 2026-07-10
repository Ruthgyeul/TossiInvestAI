import type { TotalAssetsSnapshot } from "@/lib/types";
import { formatKrw, formatPct, formatSignedKrw, signClass } from "@/lib/format";
import styles from "./Dashboard.module.css";

export function TotalAssetsCard({ data }: { data: TotalAssetsSnapshot }) {
  const { breakdown } = data;
  const total = breakdown.cashKrw + breakdown.krInvestedKrw + breakdown.usInvestedKrw;
  const cashPct = (breakdown.cashKrw / total) * 100;
  const krPct = (breakdown.krInvestedKrw / total) * 100;
  const usPct = (breakdown.usInvestedKrw / total) * 100;

  return (
    <div className={`${styles.card} ${styles.totalAssetsCard}`}>
      <div>
        <div className={styles.totalAssetsLabel}>총 자산</div>
        <div className={styles.totalAssetsValue}>{formatKrw(data.totalKrw)}</div>
        <div className={`${styles.totalAssetsChange} ${styles[signClass(data.todayChangeKrw)]}`}>
          {formatSignedKrw(data.todayChangeKrw)} ({formatPct(data.todayChangePct)}) 오늘
        </div>
      </div>

      <div className={styles.breakdownBlock}>
        <div className={styles.row}>
          <span className={styles.rowLabel}>현금</span>
          <span className={styles.rowValue}>{formatKrw(breakdown.cashKrw)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabel}>KR 투자금</span>
          <span className={styles.rowValue}>{formatKrw(breakdown.krInvestedKrw)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabel}>US 투자금</span>
          <span className={styles.rowValue}>{formatKrw(breakdown.usInvestedKrw)}</span>
        </div>
        <div className={styles.allocBar}>
          <div className={styles.allocCash} style={{ width: `${cashPct}%` }} />
          <div className={styles.allocKr} style={{ width: `${krPct}%` }} />
          <div className={styles.allocUs} style={{ width: `${usPct}%` }} />
        </div>
        <div className={styles.allocLabels}>
          <span>현금 {Math.round(cashPct)}%</span>
          <span>KR {Math.round(krPct)}%</span>
          <span>US {Math.round(usPct)}%</span>
        </div>
      </div>

      <div className={styles.statsBlock}>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>실현손익 (금일)</span>
          <span className={`${styles.rowValue} ${styles[signClass(data.realizedPnlTodayKrw)]}`}>
            {formatSignedKrw(data.realizedPnlTodayKrw)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>평가손익</span>
          <span className={`${styles.rowValue} ${styles[signClass(data.unrealizedPnlKrw)]}`}>
            {formatSignedKrw(data.unrealizedPnlKrw)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>누적 수익률 (시드 대비)</span>
          <span
            className={`${styles.rowValue} ${styles[signClass(data.cumulativeReturnPct)]}`}
            style={{ fontWeight: 700 }}
          >
            {formatPct(data.cumulativeReturnPct)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>시드 금액</span>
          <span className={styles.rowValue}>{formatKrw(data.seedKrw)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>운용 일수</span>
          <span className={styles.rowValue}>
            D+{data.operatingDays} (LIVE {data.liveDays}일)
          </span>
        </div>
      </div>

      <div className={styles.apiBlock}>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>매매 판단 모델</span>
          <span className={styles.rowValue}>{data.apiModel}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>이번달 토큰 (in/out)</span>
          <span className={styles.rowValue}>
            {data.monthlyTokensInK.toFixed(1)}k/{data.monthlyTokensOutK.toFixed(1)}k
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>API 호출 (월간)</span>
          <span className={styles.rowValue}>{data.apiCallsMonthly.toLocaleString("ko-KR")}회</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>API 비용 (월간)</span>
          <span className={styles.rowValue} style={{ fontWeight: 700 }}>
            ${data.apiCostMonthlyUsd.toFixed(2)} · {formatKrw(data.apiCostMonthlyKrw)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>API 호출 (금일)</span>
          <span className={styles.rowValue}>{data.apiCallsToday}회</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabelMuted}>API 비용 (금일)</span>
          <span className={styles.rowValue} style={{ fontWeight: 700 }}>
            ${data.apiCostTodayUsd.toFixed(2)} · {formatKrw(data.apiCostTodayKrw)}
          </span>
        </div>
      </div>
    </div>
  );
}
