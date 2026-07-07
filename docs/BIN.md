# BIN.md — 빈(Bin) 트레이딩 봇

> 빈(Bin)은 에이전트 프레임워크 없이 Claude API를 직접 호출해
> 매매를 결정하는 AI 트레이딩 봇이다.
> 이 문서는 빈의 정체성, 트레이딩 루프, AI Gateway 호출 방식,
> Prompt Caching 전략, 자기평가, 시뮬레이션 모드를 정의한다.

---

## 빈(Bin) 정체성

| 항목 | 내용 |
|------|------|
| 이름 | **빈(Bin)** |
| 역할 | AI 자동 주식 트레이딩 봇 |
| 표시 형식 | 모든 Discord·로그·리포트에서 `[빈]` 으로 표기 |
| 결정 방식 | Claude API **직접 호출** — 에이전트 프레임워크 없음 |

```
[빈] 오늘 반도체 섹터 거래량이 크게 증가했습니다.
[빈] NVDA는 단기 과열 가능성이 있습니다.
[빈] 삼성전자 75,000원에 2주 매수를 실행합니다. (RSI 반등 + 거래량 확인)
```

---

## AI Gateway 구조

매매 결정은 아래 3개 모델이 우선순위 순으로 동작한다.
모든 모델은 `core/gateway/` 모듈에서 **SDK를 직접 호출**한다.

| 순위 | 모델 | SDK / 방식 | 역할 |
|------|------|-----------|------|
| 1 | **Claude API** | `anthropic` Python SDK | 매수/매도 최종 결정 |
| 2 | **Gemini Free** | `google-genai` SDK | 뉴스 요약·보조 분석 |
| 3 | **DeepSeek Free** | OpenAI 호환 REST API | Claude 장애 시 폴백 |

```python
# core/gateway/base.py — AIGateway 추상 인터페이스
from abc import ABC, abstractmethod
from core.models import StateSnapshot, Decision

class AIGateway(ABC):
    @abstractmethod
    async def decide(self, state: StateSnapshot) -> Decision: ...

    @abstractmethod
    async def summarize_news(self, articles: list[str]) -> str: ...
```

```python
# core/trading/decision.py — AI Gateway 호출 진입점
async def get_decision(state: StateSnapshot) -> Decision:
    """
    1. 규칙 기반 필터  → Claude 호출 없이 즉시 반환 (API 비용 0)
    2. Claude 직접 호출 → 성공 시 반환
    3. Claude 실패     → DeepSeek 폴백
    """
    # Step 1: 규칙 기반 처리
    if signal := rule_based_filter(state):
        return signal

    # Step 2: Claude 직접 호출
    try:
        return await claude_gateway.decide(state)
    except (APIStatusError, APITimeoutError) as e:
        log.error("claude_failed", error=str(e))

    # Step 3: DeepSeek 폴백
    log.warning("fallback_to_deepseek")
    return await deepseek_gateway.decide(state)
```

---

## 트레이딩 루프

KR 루프와 US 루프는 `APScheduler`로 독립 실행된다.
`core/trading/loop.py` 가 루프의 단일 진입점이다.

```
[매 15분 — KR 루프 / US 루프 각각]

STEP 1. 시장 캘린더 확인
  └── market_calendar.is_open(market) == False → 스킵

STEP 2. 시장 데이터 수집 (Redis 캐시 우선)
  ├── 관심 종목 현재가·15분봉·일봉 캔들
  ├── 기술적 지표 계산 (RSI·MACD·EMA20/60·볼린저밴드)
  ├── 거래량 변화율 (전일 대비)
  ├── 환율 조회 (US 루프만)
  ├── 보유 주식 현황 + 매수가능금액
  ├── 관심 종목 내 거래량 급증 TOP10 (`toss_popular_top10` — 토스 API에 시장 전체
  │     인기 종목 랭킹 엔드포인트가 없어, 관심 종목 범위의 거래량 급증 상위로 대체)
  ├── 관심 종목 등락 비율 기반 공포/탐욕 대체 지표 (`fear_greed_index`, 0~100)
  └── 오늘 시장 이벤트 (FOMC·CPI·실적 발표 등)

STEP 3. 규칙 기반 필터 (Claude 호출 없이 처리)
  ├── RSI > 75 + 보유 중 → 매도 후보 즉시 반환
  ├── RSI < 28 + 미보유  → 매수 후보 즉시 반환
  ├── VI 발동 종목        → 제외 (KR)
  └── 신호 불명확        → STEP 4 (Claude 판단 요청)

STEP 4. StateSnapshot 구성 → Claude에 주입할 컨텍스트 빌드

STEP 5. Claude API 직접 호출 (core/gateway/claude.py)
  └── Prompt Caching L1(1h)·L2(5m) 적용
  └── 반환: Decision JSON

STEP 6. Safety Gate 검증 (docs/SAFETY.md)
  ├── 통과 → STEP 7
  └── 거부 → Discord #stock-error 알림 후 중단

STEP 7. 주문 실행 / 가상 체결 (모드에 따라 분기)
  ├── LIVE       → Toss API 실제 주문
  └── SIMULATION → 가상 체결 (실제 현재가 기준)

STEP 8. 결과 기록
  ├── PostgreSQL: trades 또는 simulation_trades
  ├── logs/trading/YYYY-MM-DD.log  ([LIVE] 또는 [SIM] 접두사)
  └── Discord: #stock-buy / #stock-sell Embed 발송
```

---

## StateSnapshot — Claude에 주입되는 컨텍스트

```json
{
  "bot": "Bin",
  "market": "KR",
  "mode": "SIMULATION",
  "strategy_version": "v1.2.0",
  "prompt_version": "system_kr_v3",
  "timestamp": "2026-07-06T10:30:00+09:00",

  "exchange_rate_krw_usd": 1382.5,

  "prices": {
    "005930": {
      "price": 75200,
      "candles_15m": [74800, 74900, 75000, 75100, 75200],
      "rsi_14": 58.3,
      "macd": 0.42,
      "macd_signal": 0.31,
      "ema_20": 74600,
      "ema_60": 73800,
      "bb_upper": 76100,
      "bb_lower": 73400,
      "volume_ratio": 1.43,
      "news_summary": "3분기 실적 예상치 상회 전망"
    }
  },

  "toss_popular_top10": ["005930", "000660"],
  "fear_greed_index": 62,
  "market_events_today": [],

  "portfolio": {
    "total_value_krw": 512000,
    "operating_funds_krw": 435200,
    "cash_buffer_krw": 76800,
    "holdings": [
      {"symbol": "005930", "qty": 2, "avg_price": 74800, "unrealized_pnl": 800}
    ],
    "open_orders": [],
    "today_realized_pnl_krw": 0,
    "api_cost_month_krw": 4200
  }
}
```

---

## Prompt Caching 전략

Claude API 호출 시 컨텍스트를 4개 레이어로 구성한다.
변하지 않는 레이어만 캐시하고, 실시간 데이터는 매번 새로 주입한다.

### 레이어 구성

| 레이어 | 내용 | 토큰 | 캐시 TTL |
|--------|------|------|----------|
| L1 시스템 프롬프트 | 빈 역할·Safety 규칙·출력 JSON 스펙 | ~800 | **1h** |
| L2 장기 기억 | 30일 거래 히스토리·Reflection 요약·종목별 수익 통계 | ~1,500 | **5m** |
| L3 실시간 데이터 | 현재가·지표·뉴스·환율·이벤트 (StateSnapshot L3) | ~2,000 | 없음 |
| L4 포트폴리오 | 보유 종목·잔고·손익·미체결 주문 (StateSnapshot L4) | ~500 | 없음 |

**레이어 순서 고정 원칙**: 정적 블록(L1·L2)이 반드시 동적 블록(L3·L4) 앞에 와야 한다.
순서가 바뀌면 캐시 prefix 규칙 위반으로 캐시가 무효화된다.

### 구현 (core/gateway/claude.py)

```python
import anthropic
from core.config import settings

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

async def call_claude(
    system_prompt: str,      # L1 — prompts/system_kr.md 또는 system_us.md
    long_term_memory: str,   # L2 — 장 시작 시 DB에서 조회, 장중 불변
    realtime_market: str,    # L3 — 매 루프 갱신
    portfolio_snapshot: str, # L4 — 매 루프 갱신
) -> dict:
    response = await _client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=settings.CLAUDE_MAX_TOKENS,

        # L1 — 1h 캐시
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }],

        messages=[{
            "role": "user",
            "content": [
                # L2 — 5m 캐시
                {
                    "type": "text",
                    "text": f"[장기 기억]\n{long_term_memory}",
                    "cache_control": {"type": "ephemeral"},
                },
                # L3 — 캐시 없음
                {
                    "type": "text",
                    "text": f"[실시간 시장 데이터]\n{realtime_market}",
                },
                # L4 — 캐시 없음
                {
                    "type": "text",
                    "text": f"[포트폴리오]\n{portfolio_snapshot}\n\n위 데이터를 분석해 매매 결정을 JSON으로 출력하라.",
                },
            ],
        }],
    )

    _record_usage(response.usage)
    return _parse_decision(response.content[0].text)
```

### 비용 효과 (Sonnet 4.6, $2/M — introductory 2026-08-31까지)

| | 호출당 | 월 1,040회 |
|-|--------|-----------|
| 캐시 미적용 | ₩13 | ₩13,520 |
| **캐시 적용** | **₩8** | **₩8,320** |
| 절감 | ₩5 (38%) | **₩5,200** |

---

## 실행·가상 주문 분기 (LIVE vs SIMULATION)

```python
# core/trading/executor.py
async def execute(decision: Decision, mode: RunMode) -> OrderResult:
    gate = await safety_gate.check(decision.to_order(), mode)
    if not gate.approved:
        await discord.send_rejection(gate, mode)
        return OrderResult.rejected(gate.reason)

    if mode == RunMode.SIMULATION:
        fill_price = await toss.get_current_price(decision.symbol)
        result = await sim_portfolio.apply(decision, fill_price)
        await log_trade(result, mode="SIMULATION")
        await discord.send_trade(result, badge="🟡 [시뮬레이션]")
    else:
        result = await toss_order.place(decision)
        await log_trade(result, mode="LIVE")
        await discord.send_trade(result)

    return result
```

---

## AI 의사결정 히스토리

모든 Claude 호출 결과를 `decisions` 테이블에 영구 저장한다.

```json
{
  "decision_id": "a3f2b1c4-...",
  "timestamp": "2026-07-06T10:31:42+09:00",
  "mode": "SIMULATION",
  "market": "KR",
  "strategy_version": "v1.2.0",
  "prompt_version": "system_kr_v3",
  "model_used": "claude-sonnet-4-6",
  "input_tokens": 1842,
  "cache_read_tokens": 2300,
  "cache_write_tokens": 0,
  "output_tokens": 312,
  "state_snapshot": {},
  "decision": { "action": "BUY", "symbol": "005930", "quantity": 2 },
  "actual_outcome": {
    "filled": true,
    "fill_price": 74800,
    "pnl_krw": 3200,
    "evaluated_at": "2026-07-06T15:35:00+09:00"
  }
}
```

---

## 자기평가 (Reflection)

장 마감 후 Claude API를 1회 호출해 오늘 매매를 자체 평가한다.

| 시장 | 실행 시각 (KST) |
|------|----------------|
| KR | 15:40 |
| US | 06:10 |

평가 항목:
- 오늘 매매가 적절했는가?
- 놓친 매수/매도 기회는 무엇인가?
- Safety Gate 거부 중 옳았던 것은?
- 내일 개선할 점은 무엇인가?

결과 저장: `reflections` 테이블 + `logs/reports/reflection_YYYY-MM-DD.md`
Discord `#stock-system` Embed 발송 (모드 뱃지 포함).

---

## 시뮬레이션 전환 체크리스트

최소 2주 운용 후 아래 항목을 모두 확인하고 `SIMULATION=false` 전환.

- [ ] Safety Gate 거부율 < 5%
- [ ] 가상 일일 손실이 `MAX_DAILY_LOSS_KRW` 미달
- [ ] Discord 알림 정상 수신 (매수·매도·거부·리포트)
- [ ] 수익률·MDD·승률 계산 오류 없음
- [ ] 로그·DB 기록 누락 없음
- [ ] `simulation_trades` / `trades` 테이블 혼용 없음

---

## 백테스트 엔진

```python
# core/strategy/backtest.py
BacktestEngine.run(
    strategy=MomentumStrategy(),
    market="KR",
    period="1Y",   # "1Y" | "3Y" | "5Y"
    initial_capital=500_000,
)
# 결과: 승률, 평균 수익률, MDD, 샤프 지수, 수익 팩터
```

관심 종목의 일봉 히스토리로 전략의 `generate_signal`을 매일 재현해 가상 체결을 누적한다.
토스증권 API에 기간 지정 캔들 조회가 없어(docs/TOSS_API.md), 보유 중인 전체 일봉 히스토리
중 최근 N거래일(1Y=252·3Y=756·5Y=1260)만 사용한다.

Discord `/backtest {strategy} {period}`는 아래 등록된 이름만 받는다
(`core/api/routes.py`의 `_BACKTEST_STRATEGIES`):

| 이름 | 전략 | 시장 |
|------|------|------|
| `kr_mean_reversion` | `MeanReversionStrategy` | KR |
| `kr_momentum` | `MomentumStrategy` | KR |
| `us_momentum` | `MomentumStrategy` | US |
| `us_overnight` | `OvernightStrategy` | US |

---

## Watchlist 관리

Claude가 시장 데이터 기반으로 관심 종목을 자동 추가·제거·우선순위 부여.
개발자는 Discord `/watchlist add {symbol}` 으로 수동 추가 가능.

---

## 시장 이벤트 캘린더

`core/events/calendar.py` 가 FOMC·CPI·실적발표·배당락 일정을 추적.
고위험 이벤트 당일: Safety Gate에서 1회 주문 한도 자동 50% 축소.

---

## 프롬프트·전략 버전 관리

모든 거래 기록에 `strategy_version` + `prompt_version` 을 함께 저장.
버전별 성과 비교로 점진적 개선.

```
strategy_version : "v1.2.0"       (semver)
prompt_version   : "system_kr_v3" (파일명 기반)
```
