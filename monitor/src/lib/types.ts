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
  operatingDays: number;
  liveDays: number;
  weeklyRebalanceDaysUntil: number;
  lastReinvestmentKrw: number;
  apiCallsToday: number;
  apiModel: string;
  tokensInK: number;
  tokensOutK: number;
  apiCostTodayUsd: number;
  apiCostTodayKrw: number;
}

export interface PnlChartSnapshot {
  periodLabel: string;
  /** Normalized 0-100 daily values (50 = flat), oldest first — mirrors the bar-height formula from the source design. */
  bars: number[];
  avgDailyReturnPct: number;
  winRatePct: number;
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
    rejectionsToday: number;
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

export interface SubStripSnapshot {
  reportTime: string;
  reportSummary: string;
  selfImprovementPendingCount: number;
  selfImprovementVersion: string;
  tossOverlapSymbols: string[];
  tossOverlapHoldingCount: number;
  tossOverlapTotalCount: number;
  fearGreedIndex: number;
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
