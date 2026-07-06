# CODING_RULES.md — 코딩 컨벤션 및 개발 규칙

---

## 언어별 역할 분리

| 레이어 | 언어·프레임워크 | 비고 |
|--------|----------------|------|
| Discord 봇 | TypeScript + Discord.js v14 | 이벤트 기반, 타입 안전성 |
| 트레이딩 코어 | Python 3.11+ (asyncio) | AI 라이브러리 생태계 |
| DB | PostgreSQL + Redis | 내구성 + 고속 캐시 |

두 서비스는 **Redis pub/sub + HTTP 내부 API**로만 통신한다.
PostgreSQL에 두 서비스가 동시 직접 접속하지 않는다.

---

## AI Gateway 원칙

**에이전트 프레임워크를 사용하지 않는다.** LangChain, AutoGen, CrewAI 등 금지.

모든 AI 호출은 `core/gateway/` 모듈에서만 수행한다.

```python
# 올바른 방식 — SDK 직접 호출
import anthropic
client = anthropic.AsyncAnthropic()
response = await client.messages.create(...)

# 금지 — 에이전트 프레임워크
from langchain.agents import AgentExecutor  # ❌
```

---

## Python 코딩 규칙

### 기본 원칙

```python
# 타입 힌트 필수
async def place_order(
    symbol: str,
    quantity: int,
    price: float | None = None,
    market: Literal["KR", "US"] = "KR",
) -> OrderResult: ...

# 비동기 전용 — 동기 블로킹 절대 금지
# ❌ requests.get(...)
# ✅ await session.get(...)

# dataclass로 도메인 모델 정의
from dataclasses import dataclass

@dataclass
class Decision:
    decision_id: str
    action: Literal["BUY", "SELL", "HOLD"]
    symbol: str
    quantity: int
    order_type: Literal["LIMIT", "MARKET"]
    price: float | None
    confidence: float
    reason: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
```

### 환경변수 — 중앙 집중 관리

```python
# core/config.py — 모든 설정의 단일 진입점
from pydantic_settings import BaseSettings
from datetime import date

class Settings(BaseSettings):
    # 토스증권
    TOSS_CLIENT_ID: str
    TOSS_CLIENT_SECRET: str
    TOSS_ACCOUNT_SEQ: str
    TOSS_BASE_URL: str = "https://openapi.tossinvest.com"

    # AI Gateway
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 512
    GEMINI_API_KEY: str
    DEEPSEEK_API_KEY: str

    # 자금
    INITIAL_SEED_KRW: int = 500_000   # 절대 변경 금지
    CASH_BUFFER_RATIO: float = 0.15

    # Safety Gate
    MAX_DAILY_LOSS_KRW: int = 50_000
    MAX_POSITION_RATIO: float = 0.50
    MAX_SINGLE_ORDER_KRW: int = 100_000
    EMERGENCY_STOP: bool = False
    KR_STOP: bool = False
    US_STOP: bool = False

    # 운영 모드
    DRY_RUN: bool = False        # true: 개발용 최소 테스트
    SIMULATION: bool = True      # true: 실전 동일 리허설 (주문만 가상)
    LOG_LEVEL: str = "INFO"

    @property
    def run_mode(self) -> str:
        if self.DRY_RUN:
            return "DRY_RUN"
        if self.SIMULATION:
            return "SIMULATION"
        return "LIVE"

    # 가격 자동 전환 (introductory → standard 2026-08-31 이후)
    @property
    def claude_input_price_per_mtok(self) -> float:
        return 2.0 if date.today().isoformat() <= "2026-08-31" else 3.0

    @property
    def claude_output_price_per_mtok(self) -> float:
        return 10.0 if date.today().isoformat() <= "2026-08-31" else 15.0

    class Config:
        env_file = ".env"

settings = Settings()
```

### 로깅

```python
import structlog

log = structlog.get_logger()

# 주문·AI 호출 관련은 항상 WARNING 이상
log.warning("order_executed",
    agent="Bin", symbol="005930", action="BUY",
    quantity=2, price=74800, decision_id="a3f2b1c4-...")

log.info("candle_fetched", symbol="005930", count=20)
log.error("claude_api_error", status=429, retry_after=2)
```

### 금액 처리

```python
# 내부 계산: KRW 정수 (float 반올림 오류 방지)
amount_krw: int = 149_600

# USD: float 허용 (소수점 거래)
amount_usd: float = 108.40

# US 포지션은 매수 시점 환율을 DB에 함께 저장
realized_pnl_krw = (
    (sell_price_usd * sell_rate) - (buy_price_usd * buy_rate)
) * quantity - commission_krw
```

### 린터·포매터

```bash
ruff format .     # 포매터
ruff check .      # 린터
mypy core/        # 타입 체커
```

---

## Prompt Caching 구현 규칙

### 레이어 순서 고정 (prefix 규칙)

캐시 블록은 반드시 **정적 레이어가 앞, 동적 레이어가 뒤** 순서여야 한다.

```
✅ 올바른 순서
  system  → [L1: 1h 캐시]
  user    → [L2: 5m 캐시] → [L3: 신선] → [L4: 신선]

❌ 잘못된 순서 (L3이 L2 앞에 오면 L2 캐시 무효화)
  user    → [L3: 신선] → [L2: 캐시] → [L4: 신선]
```

### 캐시 무효화 트리거

| 원인 | 영향 | 대응 |
|------|------|------|
| 시스템 프롬프트 텍스트 변경 | L1 전체 무효화 | 배포 전 확인 필수 |
| L2 내용 변경 | L2 이후 무효화 | 장 시작 1회만 허용 |
| 이미지 추가/제거 | 전체 무효화 | 이미지 포함 시 캐시 불가 |

### 비용 추적 (FundManager 연동)

```python
# core/gateway/claude.py
def _record_usage(usage: anthropic.types.Usage) -> None:
    fund_manager.record_api_usage(
        model=settings.CLAUDE_MODEL,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0),
    )

# core/fund/manager.py
def record_api_usage(self, model, input_tokens, output_tokens,
                     cache_read_tokens=0, cache_write_tokens=0) -> None:
    p_in  = settings.claude_input_price_per_mtok / 1_000_000
    p_out = settings.claude_output_price_per_mtok / 1_000_000
    KRW   = 1382.0  # 실시간 환율로 교체 가능

    cost_usd = (
        input_tokens        * p_in
        + cache_write_tokens * p_in * 1.25   # 5m write
        + cache_read_tokens  * p_in * 0.10   # hit
        + output_tokens      * p_out
    )
    db.insert("api_usage", {
        "model": model, "cost_usd": cost_usd,
        "cost_krw": int(cost_usd * KRW),
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
    })
```

---

## TypeScript (Discord 봇) 규칙

```typescript
// tsconfig.json: "strict": true 필수

// 모든 설정은 config.ts에서만 로드
export const config = {
  token:   process.env.DISCORD_BOT_TOKEN!,
  guildId: process.env.DISCORD_GUILD_ID!,
  channels: {
    status:  process.env.DISCORD_STATUS_CHANNEL_ID!,
    analyze: process.env.DISCORD_ANALYZE_CHANNEL_ID!,
    buy:     process.env.DISCORD_BUY_CHANNEL_ID!,
    sell:    process.env.DISCORD_SELL_CHANNEL_ID!,
    system:  process.env.DISCORD_SYSTEM_CHANNEL_ID!,
    error:   process.env.DISCORD_ERROR_CHANNEL_ID!,
    news:    process.env.DISCORD_NEWS_CHANNEL_ID!,
    log:     process.env.DISCORD_LOG_CHANNEL_ID!,
  },
}

// 모든 Discord 메시지는 Embed 형식
const embed = new EmbedBuilder()
  .setAuthor({ name: '빈(Bin)', iconURL: config.botAvatarUrl })
  .setColor(0x00b894)
  .setTimestamp()

// 비동기 함수는 try/catch 필수
try {
  await channel.send({ embeds: [embed] })
} catch (err) {
  logger.error('Discord send failed', { err, channelId: channel.id })
}
```

---

## 의존성

### Python (requirements.txt)

```
# AI Gateway
anthropic>=0.30
google-generativeai>=0.8     # Gemini
openai>=1.0                  # DeepSeek (OpenAI 호환)

# 설정·비동기·DB
pydantic-settings>=2.0
aiohttp>=3.9
asyncpg>=0.29
redis[asyncio]>=5.0
SQLAlchemy[asyncio]>=2.0

# 스케줄러·로깅
APScheduler>=3.10
structlog>=24.0

# 시장 데이터·분석
pandas>=2.0
ta>=0.11                     # RSI·MACD·EMA·볼린저밴드
matplotlib>=3.8              # 리포트 그래프

# 헬스 모니터링
psutil>=5.9

# Discord 알림 (헬스 모니터링용)
discord.py>=2.4

# 환경변수
python-dotenv>=1.0

# 테스트·품질
pytest>=8.0
pytest-asyncio>=0.23
aioresponses>=0.7          # toss/client.py 등 aiohttp 호출 목업
fakeredis>=2.20            # Redis 캐시·Rate Limit 로직 인메모리 테스트
mypy>=1.8
ruff>=0.4
```

### Node.js (package.json)

```json
{
  "dependencies": {
    "discord.js": "^14.0.0",
    "dotenv": "^16.0.0",
    "ioredis": "^5.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/node": "^20.0.0",
    "ts-node": "^10.0.0",
    "tsup": "^8.0.0"
  }
}
```

---

## 개발 순서

```
Phase 1 — 기반 구성 (DRY_RUN=true 유지)
  1.  .env 작성, PostgreSQL + Redis 설치, DB 스키마 생성
  2.  core/config.py → Settings 클래스 단위 테스트
  3.  toss/auth.py → 토큰 발급 확인
  4.  toss/market.py → KR(005930) + US(AAPL) 현재가 조회
  5.  toss/market.py → market-calendar KR·US 응답 파싱 검증

Phase 2 — 핵심 모듈
  6.  toss/account.py → 계좌·보유주식 조회
  7.  fund/manager.py → 자금 배분·API 비용 기록 단위 테스트
  8.  safety/gate.py → Safety Gate 구현·단위 테스트 (KR·US 시나리오)
  9.  toss/order.py → DRY_RUN=true 주문 테스트

Phase 3 — AI Gateway
  10. gateway/claude.py → Prompt Caching 포함 호출 테스트
  11. gateway/gemini.py → 뉴스 요약 테스트
  12. gateway/deepseek.py → 폴백 테스트
  13. trading/decision.py → StateSnapshot → Decision JSON 통합 테스트

Phase 4 — 루프·Discord
  14. trading/loop.py → KR·US 트레이딩 루프 통합 테스트
  15. discord-bot/ → 봇 연결, /status /fund /health 명령 테스트
  16. #status 채널 고정 Embed + 주기적 edit 구현
  17. report/generator.py + chart.py → 리포트 생성 테스트

Phase 5 — 실전 전환
  18. Safety Gate + FundManager 완전 검증
  19. SIMULATION=true → 최소 2주 이상 시뮬레이션 운용
        - 실전과 동일하게 돌리되 실제 주문 없음
        - simulation_trades·수익률·Safety Gate 거부 패턴 분석
        - 문제 없으면 SIMULATION=false → 소액 실제 주문 1주 테스트
  20. 7일 모니터링 → 이상 없으면 정식 운용
```

---

## Git 규칙

```gitignore
.env
*.log
logs/
backups/
data/backtest/
__pycache__/
*.pyc
node_modules/
dist/
```

커밋 메시지 형식:
```
feat: Safety Gate 종목당 상한 50% 검증 추가
fix: Prompt Caching L2 TTL 5m 적용 오류 수정
docs: TOSS_API.md 에러 코드 목록 보완
refactor: gateway/claude.py 재시도 로직 분리
```

---

## 확장성 원칙

- 새 전략 → `strategy/base.py`의 `BaseStrategy` 상속
- 새 AI 모델 → `gateway/base.py`의 `AIGateway` 구현 후 `decision.py`에 등록
- 새 시장(JP 등) → `strategy/{market}/` 추가, Safety Gate는 공통 사용
- 새 Discord 채널 → `.env` 채널 ID 추가 + `config.ts` 확장 (채널 삭제 불가)
