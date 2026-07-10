import type { ChartPeriod, MonitorSnapshot } from "./types";

/** "D-14", "D-11", ... "오늘" (or "H-"/"지금" for the hourly period) — every 3rd bar, mirroring the source design's `offsetLabels`. */
function offsetLabels(n: number, unit: string, nowLabel: string, spanUnits?: number): string[] {
  const span = spanUnits ?? n - 1;
  return Array.from({ length: n }, (_, i) => {
    const offset = Math.round((span * (n - 1 - i)) / (n - 1));
    return i === n - 1 ? nowLabel : i % 3 === 0 ? `${unit}-${offset}` : "";
  });
}

const BAR_POOL = [
  58, 62, 45, 70, 48, 30, 55, 80, 62, 40, 25, 65, 90, 50, 68, 35, 72, 58, 47, 63, 66, 44, 78, 53, 52,
  61, 47, 58, 66, 40, 71, 55, 49, 63, 36, 68,
];

/** Converts the source design's 0-100 demo pool into plausible KRW day-over-day deltas. */
function genBars(n: number, offset: number, krwPerUnit: number): number[] {
  return Array.from({ length: n }, (_, i) => (BAR_POOL[(offset + i) % BAR_POOL.length] - 50) * krwPerUnit);
}

function genBenchmarkBars(bars: number[], ratio: number): number[] {
  return bars.map((v) => Math.round(v * ratio));
}

function chartFooter(bars: number[]) {
  const up = bars.filter((b) => b > 0);
  const down = bars.filter((b) => b < 0);
  const totalUpKrw = up.reduce((sum, b) => sum + b, 0);
  const totalDownKrw = down.reduce((sum, b) => sum + b, 0);
  return { totalUpKrw, upDays: up.length, totalDownKrw, downDays: down.length, netKrw: totalUpKrw + totalDownKrw };
}

const FULL_BARS = genBars(21, 0, 8000);
const RECENT_BARS = genBars(15, 6, 9000);
const HOURLY_BARS = genBars(24, 9, 2000);

const CHART_PERIODS: ChartPeriod[] = [
  {
    label: "전체",
    bars: FULL_BARS,
    xLabels: offsetLabels(21, "D", "오늘", 60),
    avgDailyReturnPct: 0.42,
    winRatePct: 60,
    benchmarkBars: genBenchmarkBars(FULL_BARS, 0.6),
  },
  {
    label: "최근 15일",
    bars: RECENT_BARS,
    xLabels: offsetLabels(15, "D", "오늘", 15),
    avgDailyReturnPct: 0.55,
    winRatePct: 67,
    benchmarkBars: genBenchmarkBars(RECENT_BARS, 0.6),
  },
  {
    label: "일일",
    bars: HOURLY_BARS,
    xLabels: offsetLabels(24, "H", "지금", 24),
    avgDailyReturnPct: 0.18,
    winRatePct: 63,
    // 실데이터에서도 관심 종목 일봉만 있고 시간별 지수 데이터는 없어 벤치마크 라인을 그리지 않는다.
    benchmarkBars: [],
  },
];

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
      perfStats: [
        { label: "알파", value: "+2.1%p · KOSPI 대비", tone: "positive" },
        { label: "알파", value: "+1.4%p · S&P500 대비", tone: "positive" },
        { label: "승률", value: "60% · 최근 30건", tone: "neutral" },
        { label: "체결률", value: "98% · 47/48건", tone: "neutral" },
        { label: "손익비", value: "1.8 · 평균 수익/손실", tone: "positive" },
        { label: "샤프지수", value: "1.42 · 최근 30일", tone: "neutral" },
        { label: "연속수익", value: "5일 · 진행 중", tone: "positive" },
      ],
      riskStats: [
        { label: "집중도", value: "정상 · NVDA 10.7%", tone: "good" },
        { label: "변동성", value: "보통 · 최근 5일", tone: "warn" },
        { label: "MDD", value: "-3.2% · 시드 대비", tone: "bad" },
        { label: "VaR (95%)", value: "-₩842,000 · 1일 기준", tone: "bad" },
      ],
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
      seedKrw: 50000000,
      operatingDays: 58,
      liveDays: 44,
      apiModel: "Sonnet",
      apiCallsToday: 47,
      apiCostTodayUsd: 4.82,
      apiCostTodayKrw: 6706,
      monthlyTokensInK: 3012.4,
      monthlyTokensOutK: 512.1,
      apiCallsMonthly: 1410,
      apiCostMonthlyUsd: 144.6,
      apiCostMonthlyKrw: 201180,
    },
    chart: {
      periods: CHART_PERIODS,
      ...chartFooter(FULL_BARS),
    },
    systemHealth: {
      errorCountToday: 0,
      lastHeartbeatSecondsAgo: 3,
      services: [
        { name: "core", status: "ok", detail: "14d 6h" },
        { name: "discord-bot", status: "ok", detail: "14d 6h" },
        { name: "scheduler", status: "ok", detail: "14d 6h" },
        { name: "DB·Redis", status: "ok", detail: "정상" },
        { name: "Toss API", status: "ok", detail: "정상" },
        { name: "매매 판단 모델 API", status: "ok", detail: "정상" },
      ],
      logs: [
        { time: "14:32", level: "INFO", message: "하트비트 정상 · core" },
        {
          time: "14:28",
          level: "INFO",
          message:
            "삼성전자 BUY 주문 체결 완료 — 체결가 78,400원, 수량 5주, 슬리피지 0.12%, 전략 시그널 신뢰도 82%, Safety Gate 통과, 포지션 비중 재계산 완료, 다음 리밸런싱까지 D-3",
        },
        { time: "14:02", level: "WARN", message: "NVDA Safety Gate 거부" },
        { time: "11:47", level: "WARN", message: "TSLA Safety Gate 거부" },
        { time: "09:00", level: "INFO", message: "정기 리포트 생성 완료" },
        { time: "03:00", level: "INFO", message: "DB 자동 백업 성공" },
        { time: "00:00", level: "INFO", message: "자정 헬스체크 통과" },
        { time: "어제 23:30", level: "INFO", message: "야간 모니터링 정상" },
        { time: "어제 21:00", level: "INFO", message: "US 장 개장 감지" },
        { time: "어제 18:00", level: "INFO", message: "KR 장 마감, 정산 완료" },
        { time: "어제 12:30", level: "INFO", message: "전략 파라미터 재적재 완료" },
        { time: "어제 09:00", level: "INFO", message: "정기 리포트 생성 완료" },
      ],
      safetyGate: {
        passRateLabel: "11/11 통과",
        rejections: [
          { time: "14:02", message: "NVDA · 단일종목 한도 초과" },
          { time: "11:47", message: "TSLA · 일일 손실한도 근접" },
          { time: "09:20", message: "SOXL · 레버리지 ETF 거래제한" },
          { time: "어제 22:15", message: "TSLA · 변동성 급등 감지" },
          { time: "어제 16:40", message: "NAVER · 유동성 부족 경고" },
        ],
      },
      selfAssessment: {
        time: "어제 23:50",
        summary:
          "KR 전략 안정적, NVDA 비중 확대 검토 제안. 변동성 구간은 보수적 진입 유효하며 익절 라인은 기존 대비 2%p 상향 조정 권고, 당분간 현금 비중도 소폭 확대 유지 필요.",
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
      {
        sentiment: "호재",
        text: "삼성전자, 2분기 반도체 부문 흑자전환 전망 발표 이후 외국인 수급 유입세 지속되며 목표가 상향 리포트 잇따라 발간",
      },
      {
        sentiment: "주의",
        text: "Fed 위원 발언, 9월 금리 인하 기대 후퇴하며 채권시장 변동성 확대, 달러 강세 전환 우려도 동시에 제기되는 상황",
      },
      {
        sentiment: "호재",
        text: "NVDA, 데이터센터向 신규 수주 발표와 함께 차세대 GPU 양산 일정 공개, 협력사 실적 전망치도 동반 상향",
      },
    ],
    events: [
      { label: "7/10 (금) FOMC 의사록 공개", risk: "고위험" },
      { label: "7/11 (토) NVDA 실적발표", risk: "일반", daysUntilLabel: "D+2" },
      { label: "7/14 (화) 미 CPI 발표", risk: "고위험" },
    ],
  };
}
