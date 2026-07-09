import type { MonitorSnapshot, NewsSentiment } from "./types";

/**
 * core/api/monitor_snapshot.py returns camelCase keys matching MonitorSnapshot almost
 * field-for-field by design — the one exception is `news`, which core intentionally
 * leaves unclassified (`{symbol, text}`) since sentiment tagging is a display concern,
 * not trading logic. Everything here is defensive against a partial/malformed response
 * crossing the network boundary rather than crashing the kiosk.
 */

const POSITIVE_KEYWORDS = ["상승", "성장", "호조", "흑자", "개선", "수주", "확대", "강세", "기대", "돌파", "호재"];
const NEGATIVE_KEYWORDS = ["하락", "급락", "우려", "리스크", "규제", "손실", "적자", "약세", "후퇴", "경고", "악재"];

function classifySentiment(text: string): NewsSentiment {
  const positive = POSITIVE_KEYWORDS.some((kw) => text.includes(kw));
  const negative = NEGATIVE_KEYWORDS.some((kw) => text.includes(kw));
  if (negative && !positive) return "악재";
  if (positive && !negative) return "호재";
  return "주의";
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function mapNews(raw: unknown): MonitorSnapshot["news"] {
  return asArray<{ symbol?: string; text?: string }>(raw)
    .filter((item) => typeof item.text === "string" && item.text.length > 0)
    .map((item) => {
      const text = item.text as string;
      const labeled = item.symbol ? `${item.symbol}: ${text}` : text;
      return { sentiment: classifySentiment(text), text: labeled };
    });
}

/** Throws if the response is missing structurally required top-level sections. */
export function mapCoreSnapshot(raw: Record<string, unknown>): MonitorSnapshot {
  const header = asRecord(raw.header);
  const subStrip = asRecord(raw.subStrip);
  const totalAssets = asRecord(raw.totalAssets);
  const breakdown = asRecord(totalAssets.breakdown);
  const chart = asRecord(raw.chart);
  const systemHealth = asRecord(raw.systemHealth);
  const safetyGate = asRecord(systemHealth.safetyGate);
  const selfAssessment = asRecord(systemHealth.selfAssessment);

  return {
    generatedAt: typeof raw.generatedAt === "string" ? raw.generatedAt : new Date().toISOString(),
    header: {
      usdKrw: Number(header.usdKrw ?? 0),
      krMarketStatus: String(header.krMarketStatus ?? "-"),
      usMarketStatus: String(header.usMarketStatus ?? "-"),
      strategyVersion: String(header.strategyVersion ?? "-"),
      promptVersion: String(header.promptVersion ?? "-"),
    },
    subStrip: {
      reportTime: String(subStrip.reportTime ?? "-"),
      reportSummary: String(subStrip.reportSummary ?? "-"),
      selfImprovementPendingCount: Number(subStrip.selfImprovementPendingCount ?? 0),
      selfImprovementVersion: String(subStrip.selfImprovementVersion ?? "-"),
      tossOverlapSymbols: asArray<string>(subStrip.tossOverlapSymbols),
      tossOverlapHoldingCount: Number(subStrip.tossOverlapHoldingCount ?? 0),
      tossOverlapTotalCount: Number(subStrip.tossOverlapTotalCount ?? 0),
      fearGreedIndex: typeof subStrip.fearGreedIndex === "number" ? subStrip.fearGreedIndex : null,
      fearGreedLabel: String(subStrip.fearGreedLabel ?? "데이터 없음"),
    },
    totalAssets: {
      totalKrw: Number(totalAssets.totalKrw ?? 0),
      todayChangeKrw: Number(totalAssets.todayChangeKrw ?? 0),
      todayChangePct: Number(totalAssets.todayChangePct ?? 0),
      breakdown: {
        cashKrw: Number(breakdown.cashKrw ?? 0),
        krInvestedKrw: Number(breakdown.krInvestedKrw ?? 0),
        usInvestedKrw: Number(breakdown.usInvestedKrw ?? 0),
      },
      realizedPnlTodayKrw: Number(totalAssets.realizedPnlTodayKrw ?? 0),
      unrealizedPnlKrw: Number(totalAssets.unrealizedPnlKrw ?? 0),
      cumulativeReturnPct: Number(totalAssets.cumulativeReturnPct ?? 0),
      operatingDays: Number(totalAssets.operatingDays ?? 0),
      liveDays: Number(totalAssets.liveDays ?? 0),
      weeklyRebalanceDaysUntil: Number(totalAssets.weeklyRebalanceDaysUntil ?? 0),
      lastReinvestmentKrw: Number(totalAssets.lastReinvestmentKrw ?? 0),
      apiCallsToday: Number(totalAssets.apiCallsToday ?? 0),
      apiModel: String(totalAssets.apiModel ?? "-"),
      tokensInK: Number(totalAssets.tokensInK ?? 0),
      tokensOutK: Number(totalAssets.tokensOutK ?? 0),
      apiCostTodayUsd: Number(totalAssets.apiCostTodayUsd ?? 0),
      apiCostTodayKrw: Number(totalAssets.apiCostTodayKrw ?? 0),
    },
    chart: {
      periodLabel: String(chart.periodLabel ?? "전체"),
      bars: asArray<number>(chart.bars),
      avgDailyReturnPct: Number(chart.avgDailyReturnPct ?? 0),
      winRatePct: Number(chart.winRatePct ?? 0),
      totalUpKrw: Number(chart.totalUpKrw ?? 0),
      upDays: Number(chart.upDays ?? 0),
      totalDownKrw: Number(chart.totalDownKrw ?? 0),
      downDays: Number(chart.downDays ?? 0),
      netKrw: Number(chart.netKrw ?? 0),
    },
    systemHealth: {
      errorCountToday: Number(systemHealth.errorCountToday ?? 0),
      lastHeartbeatSecondsAgo: Number(systemHealth.lastHeartbeatSecondsAgo ?? 0),
      services: asArray(systemHealth.services),
      logs: asArray(systemHealth.logs),
      safetyGate: {
        passRateLabel: String(safetyGate.passRateLabel ?? "-"),
        rejections: asArray(safetyGate.rejections),
      },
      selfAssessment: {
        time: String(selfAssessment.time ?? "-"),
        summary: String(selfAssessment.summary ?? "-"),
      },
    },
    positions: asArray(raw.positions),
    aiDecisions: asArray(raw.aiDecisions),
    aiDecisionsCountToday: Number(raw.aiDecisionsCountToday ?? 0),
    news: mapNews(raw.news),
    events: asArray(raw.events),
  };
}
