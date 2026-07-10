export type Market = "KR" | "US";

export interface AssetBreakdown {
  cashKrw: number;
  krInvestedKrw: number;
  usInvestedKrw: number;
}

export interface TotalAssetsSnapshot {
  totalKrw: number;
  todayChangeKrw: number;
  todayChangePct: number;
  breakdown: AssetBreakdown;
  realizedPnlTodayKrw: number;
  unrealizedPnlKrw: number;
  cumulativeReturnPct: number;
  seedKrw: number;
  operatingDays: number;
  liveDays: number;
  apiModel: string;
  apiCallsToday: number;
  apiCostTodayUsd: number;
  apiCostTodayKrw: number;
  monthlyTokensInK: number;
  monthlyTokensOutK: number;
  apiCallsMonthly: number;
  apiCostMonthlyUsd: number;
  apiCostMonthlyKrw: number;
}

export interface ChartPeriod {
  label: string;
  /** Day-over-day (or hour-over-hour, for the "일일" period) KRW deltas, oldest first. */
  bars: number[];
  /** X-axis tick per bar — most are "", every ~3rd bar gets a date/hour label, last is "오늘"/"지금". */
  xLabels: string[];
  avgDailyReturnPct: number;
  winRatePct: number;
  /** Blended KR/US proxy-index KRW-equivalent deltas, same length as `bars` — empty when no proxy data exists. */
  benchmarkBars: number[];
}

export interface PnlChartSnapshot {
  /** [전체, 최근 15일, 일일] — the dashboard rotates through these every 5s. */
  periods: ChartPeriod[];
  totalUpKrw: number;
  upDays: number;
  totalDownKrw: number;
  downDays: number;
  netKrw: number;
}

export type ServiceStatus = "ok" | "warn" | "error";

export interface ServiceHealth {
  name: string;
  status: ServiceStatus;
  detail: string;
}

export type LogLevel = "INFO" | "WARN" | "ERROR";

export interface LogEntry {
  time: string;
  level: LogLevel;
  message: string;
}

export interface SafetyRejection {
  time: string;
  message: string;
}

export interface SystemHealthSnapshot {
  errorCountToday: number;
  lastHeartbeatSecondsAgo: number;
  services: ServiceHealth[];
  logs: LogEntry[];
  safetyGate: {
    passRateLabel: string;
    rejections: SafetyRejection[];
  };
  selfAssessment: {
    time: string;
    summary: string;
  };
}

export interface Position {
  market: Market;
  symbol: string;
  quantityLabel: string;
  returnPct: number;
}

export type TradeAction = "BUY" | "SELL" | "HOLD";

export interface AiDecision {
  time: string;
  action: TradeAction;
  symbol: string;
  confidencePct: number;
}

export type NewsSentiment = "호재" | "주의" | "악재";

export interface NewsHeadline {
  sentiment: NewsSentiment;
  text: string;
}

export type EventRisk = "고위험" | "일반";

export interface MarketEvent {
  label: string;
  risk: EventRisk;
  daysUntilLabel?: string;
}

export interface HeaderSnapshot {
  usdKrw: number;
  krMarketStatus: string;
  usMarketStatus: string;
  strategyVersion: string;
  promptVersion: string;
}

export type StatTone = "positive" | "negative" | "neutral" | "good" | "warn" | "bad";

export interface Stat {
  label: string;
  value: string;
  tone: StatTone;
}

export interface SubStripSnapshot {
  reportTime: string;
  reportSummary: string;
  /** Rotating "성과" cards — alpha vs proxy index, win rate, fill rate, profit factor, Sharpe, win streak. */
  perfStats: Stat[];
  /** Rotating "리스크" cards — concentration, volatility, MDD, VaR. */
  riskStats: Stat[];
  /** null when core has not run a trading loop tick yet (no state_snapshot to derive it from). */
  fearGreedIndex: number | null;
  fearGreedLabel: string;
}

export interface MonitorSnapshot {
  generatedAt: string;
  header: HeaderSnapshot;
  subStrip: SubStripSnapshot;
  totalAssets: TotalAssetsSnapshot;
  chart: PnlChartSnapshot;
  systemHealth: SystemHealthSnapshot;
  positions: Position[];
  aiDecisions: AiDecision[];
  aiDecisionsCountToday: number;
  news: NewsHeadline[];
  events: MarketEvent[];
}
