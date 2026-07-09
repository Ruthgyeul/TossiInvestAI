import type { MonitorSnapshot } from "./types";

/**
 * Placeholder data shaped exactly like a future `GET /api/v1/monitor/snapshot`
 * response from core's internal API (see docs/INTERNAL_API.md). Swap
 * `getMockSnapshot()` for a real fetch once that endpoint exists — see
 * monitor/README.md "데이터 연동".
 */
export function getMockSnapshot(): MonitorSnapshot {
  return {
    generatedAt: new Date().toISOString(),
    header: {
      usdKrw: 1391.2,
      krMarketStatus: "장중",
      usMarketStatus: "장마감",
      strategyVersion: "v1.4",
      promptVersion: "v3.2",
    },
    subStrip: {
      reportTime: "09:00",
      reportSummary: "KR 강세 지속, 반도체 업황 개선 코멘트",
      selfImprovementPendingCount: 1,
      selfImprovementVersion: "v1.5",
      tossOverlapSymbols: ["삼성전자", "NVDA", "AAPL"],
      tossOverlapHoldingCount: 3,
      tossOverlapTotalCount: 10,
      fearGreedIndex: 54,
      fearGreedLabel: "중립",
    },
    totalAssets: {
      totalKrw: 52384050,
      todayChangeKrw: 842150,
      todayChangePct: 1.63,
      breakdown: {
        cashKrw: 8120000,
        krInvestedKrw: 26500000,
        usInvestedKrw: 17764050,
      },
      realizedPnlTodayKrw: 312000,
      unrealizedPnlKrw: 530150,
      cumulativeReturnPct: 4.77,
      operatingDays: 58,
      liveDays: 44,
      weeklyRebalanceDaysUntil: 3,
      lastReinvestmentKrw: 186000,
      apiCallsToday: 47,
      apiModel: "Sonnet",
      tokensInK: 128.4,
      tokensOutK: 22.1,
      apiCostTodayUsd: 4.82,
      apiCostTodayKrw: 6706,
    },
    chart: {
      periodLabel: "전체",
      bars: [
        58, 62, 45, 70, 48, 30, 55, 80, 62, 40, 25, 65, 90, 50, 68, 35, 72, 58,
        47, 63,
      ],
      avgDailyReturnPct: 0.42,
      winRatePct: 60,
      totalUpKrw: 2184600,
      upDays: 12,
      totalDownKrw: -716200,
      downDays: 8,
      netKrw: 1468400,
    },
    systemHealth: {
      errorCountToday: 0,
      lastHeartbeatSecondsAgo: 3,
      services: [
        { name: "core", status: "ok", detail: "14d 6h" },
        { name: "discord-bot", status: "ok", detail: "14d 6h" },
        { name: "scheduler", status: "ok", detail: "14d 6h" },
        { name: "DB·Redis", status: "ok", detail: "정상" },
      ],
      logs: [
        { time: "14:32", level: "INFO", message: "하트비트 정상 · core" },
        { time: "14:28", level: "INFO", message: "삼성전자 BUY 주문 체결" },
        { time: "14:02", level: "WARN", message: "NVDA Safety Gate 거부" },
        { time: "09:00", level: "INFO", message: "정기 리포트 생성 완료" },
        { time: "03:00", level: "INFO", message: "DB 자동 백업 성공" },
        { time: "00:00", level: "INFO", message: "자정 헬스체크 통과" },
      ],
      safetyGate: {
        passRateLabel: "11/11 통과",
        rejectionsToday: 2,
        rejections: [
          { time: "14:02", message: "NVDA · 단일종목 한도 초과" },
          { time: "11:47", message: "TSLA · 일일 손실한도 근접" },
          { time: "09:20", message: "SOXL · 레버리지 ETF 거래제한" },
          { time: "어제 22:15", message: "TSLA · 변동성 급등 감지" },
          { time: "어제 16:40", message: "NAVER · 유동성 부족 경고" },
          { time: "어제 10:05", message: "AAPL · 신뢰도 임계치 미달" },
        ],
      },
      selfAssessment: {
        time: "어제 23:50",
        summary: "KR 전략 안정적, NVDA 비중 확대 검토 제안",
      },
    },
    positions: [
      { market: "US", symbol: "NVDA", quantityLabel: "6주", returnPct: 10.7 },
      { market: "KR", symbol: "삼성전자", quantityLabel: "30주", returnPct: 4.6 },
      { market: "US", symbol: "AAPL", quantityLabel: "10주", returnPct: 3.8 },
      {
        market: "KR",
        symbol: "SK하이닉스",
        quantityLabel: "12주",
        returnPct: 3.8,
      },
      { market: "US", symbol: "MSFT", quantityLabel: "4주", returnPct: -1.7 },
      { market: "KR", symbol: "NAVER", quantityLabel: "8주", returnPct: -3.3 },
      { market: "KR", symbol: "LG엔솔", quantityLabel: "5주", returnPct: -4.1 },
    ],
    aiDecisionsCountToday: 12,
    aiDecisions: [
      { time: "14:28", action: "BUY", symbol: "삼성전자", confidencePct: 82 },
      { time: "14:15", action: "HOLD", symbol: "NVDA", confidencePct: 61 },
      { time: "13:52", action: "SELL", symbol: "NAVER", confidencePct: 74 },
      { time: "13:30", action: "BUY", symbol: "LG엔솔", confidencePct: 68 },
      { time: "13:04", action: "HOLD", symbol: "TSLA", confidencePct: 58 },
      { time: "12:40", action: "SELL", symbol: "AAPL", confidencePct: 65 },
      {
        time: "12:15",
        action: "HOLD",
        symbol: "SK하이닉스",
        confidencePct: 55,
      },
    ],
    news: [
      { sentiment: "호재", text: "삼성전자, 2분기 반도체 부문 흑자전환 전망" },
      { sentiment: "주의", text: "Fed 위원 발언, 9월 금리 인하 기대 후퇴" },
      { sentiment: "호재", text: "NVDA, 데이터센터向 신규 수주 발표" },
    ],
    events: [
      { label: "7/10 (금) FOMC 의사록 공개", risk: "고위험" },
      { label: "7/11 (토) NVDA 실적발표", risk: "일반", daysUntilLabel: "D+2" },
      { label: "7/14 (화) 미 CPI 발표", risk: "고위험" },
    ],
  };
}
