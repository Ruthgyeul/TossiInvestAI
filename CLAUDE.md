# CLAUDE.md — 빈(Bin) AI 트레이딩 봇

> 이 파일은 이 프로젝트의 최상위 컨텍스트 문서다.
> 코드를 작성하거나 수정하기 전에 반드시 이 파일과 `docs/` 하위 문서를 먼저 읽는다.

---

## 프로젝트 한 줄 요약

Raspberry Pi 5에서 24/7 실행되는 AI 자동 주식 트레이딩 봇.
한국장(KRX)과 미국장(US)을 동시에 운용하며, 모든 상태와 결정을 Discord로 공유한다.

---

## 하드웨어

| 항목 | 사양 |
|------|------|
| 보드 | Raspberry Pi 5 **8GB RAM** |
| 저장장치 | **256GB SSD** |
| OS | **Ubuntu 24.04 LTS** |
| 운영 | 24/7 무중단 |

---

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| Discord 봇 | **Discord.js v14 + TypeScript** | 24/7 상시 실행, systemd 관리 |
| 트레이딩 코어 | **Python 3.11+ (asyncio)** | 매매 루프·분석·리포트 |
| AI 결정 | **Claude API** (anthropic SDK) | 매수/매도 최종 판단, 직접 호출 |
| AI 보조 | **Gemini Free Tier** | 뉴스 요약, 보조 분석 |
| AI 폴백 | **DeepSeek Free Tier** | Claude 장애 시 대체 |
| DB | **PostgreSQL + Redis** | 주 데이터 + 캐시/Rate Limit |
| 거래소 | **토스증권 Open API** | 주문·시세·계좌 |

---

## AI 호출 방식 — 핵심 원칙

**Claude API는 Python 코드 안에서 직접 호출한다. 에이전트 프레임워크를 사용하지 않는다.**

```
❌ 사용하지 않는 것
   - Claude Code를 런타임에 실행
   - OpenClaw, LangChain, AutoGen 등 에이전트 프레임워크
   - 에이전트에게 루프/재시도/툴 호출 주도권 위임

✅ 사용하는 것
   - anthropic Python SDK로 messages.create() 직접 호출
   - 호출 조건·빈도·모델을 Python 코드로 완전 제어
   - Prompt Caching으로 비용 최적화 (L1·L2 캐시)
```

**이유**: 에이전트 프레임워크는 내부적으로 반복 호출·재시도·툴 실행을 자율 결정하므로
API 비용이 예측 불가능하게 폭증한다. 직접 호출 방식은 호출 시점과 횟수를 코드가 완전히 통제한다.

### 런타임 호출 규칙

```python
# core/trading/decision.py — 이 함수만이 Claude를 호출할 수 있다
async def call_claude(state: StateJSON) -> Decision:
    # 1. 규칙 기반으로 처리 가능하면 Claude 호출 없이 반환
    if signal := rule_based_filter(state):
        return signal

    # 2. 모호한 경우에만 API 호출
    response = await anthropic_client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=settings.CLAUDE_MAX_OUTPUT_TOKENS,
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        messages=build_messages(state),  # L2 캐시 + L3·L4 신선 주입
    )

    # 3. 사용량 즉시 기록
    record_api_usage(response.usage)
    return parse_decision(response)
```

---

## 초기 자금

| 항목 | 값 |
|------|----|
| 시드 | **500,000 KRW** (외부 추입 없음) |
| 운용 시작 전 | **SIMULATION 모드 최소 2주** 필수 |
| 운용 자금 | 시드의 **85%** → 425,000 KRW (KR·US 봇 자율 배분) |
| 현금 버퍼 | 시드의 **15%** → 75,000 KRW (수수료·API 비용·급등 대응) |
| 종목당 상한 | 운용 자금의 **50%** 이하 (하드 제약) |
| 수익 목표 | 수익금으로 Claude API 비용 충당 → 나머지 재투자 |

---

## 문서 구조

```
CLAUDE.md                  ← 지금 이 파일 (최상위, 가장 먼저 읽기)
docs/
├── ARCHITECTURE.md        ← 시스템 구조, 디렉토리 트리, DB 스키마, systemd
├── BIN.md                 ← 빈(Bin) 정체성, 트레이딩 루프, AI Gateway, Prompt Caching
├── DISCORD.md             ← 채널 구성, Slash 명령어, Embed 포맷, TS 구현
├── REPORT.md              ← 리포트 스케줄(6회/일), 필수 항목, matplotlib 그래프
├── SAFETY.md              ← Safety Gate 10개 조건, 긴급 정지, 하드 금지 사항
├── LOGGING.md             ← 거래 로그 포맷, 에러 로그, DB 백업, 헬스 모니터링
├── FUND_MANAGER.md        ← 자금 배분, 수익 재배분, API 비용 추적
├── TOSS_API.md            ← 토스증권 API 전체 스펙, Rate Limit, 에러 코드
├── CODING_RULES.md        ← 코딩 컨벤션, 의존성, Prompt Caching 구현, 개발 순서
├── SELF_IMPROVEMENT.md    ← 자기개선 루프, 버전 관리·롤백, 배포 승인 절차
├── INTERNAL_API.md        ← discord-bot ↔ core 내부 통신 스펙 (HTTP API, Redis pub/sub)
└── DEPLOYMENT.md          ← 라즈베리파이 배포·업데이트·백업·롤백 절차
```

---

## 절대 규칙

1. **모든 주문은 Safety Gate를 통과해야 한다** → `docs/SAFETY.md`
2. **`.env` 파일은 절대 git에 커밋하지 않는다**
3. **`INITIAL_SEED_KRW` 값은 변경하지 않는다** (손익 계산 기준점)
4. **미국장 시간은 하드코딩 금지** — 항상 `/api/v1/market-calendar/US` 기준
5. **Claude API는 규칙 기반 처리 가능한 신호에는 호출하지 않는다** (비용 절감)
6. **거래 로그는 절대 삭제하지 않는다** → `docs/LOGGING.md`
7. **Discord 메시지는 모두 Embed 형식으로 전송한다** → `docs/DISCORD.md`
8. **채널 삭제는 불가능하다** (봇은 채널 생성만 가능)
9. **모든 코드는 확장성과 지속 가능성을 우선한다** → `docs/CODING_RULES.md`
10. **에이전트 프레임워크는 사용하지 않는다** — Claude API를 코드에서 직접 호출한다
11. **실전 전환 전 SIMULATION 모드 2주 이상 필수** → 실전 DB와 시뮬레이션 DB는 절대 혼용하지 않는다
