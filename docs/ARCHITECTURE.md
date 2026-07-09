# ARCHITECTURE.md — 시스템 구조

---

## 하드웨어

| 항목 | 사양 |
|------|------|
| 보드 | Raspberry Pi 5 **8GB RAM** |
| 저장장치 | **256GB SSD** |
| OS | **Ubuntu 24.04 LTS** |
| 운영 | 24/7 무중단 |

---

## 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 5 (8GB)                     │
│                      Ubuntu 24.04 LTS                        │
│                                                              │
│  ┌───────────────────────┐   ┌────────────────────────────┐  │
│  │     Discord Bot       │   │       Trading Core         │  │
│  │  Discord.js v14 + TS  │   │   Python 3.11+ asyncio     │  │
│  │  bin-discord.service  │   │   bin-core.service         │  │
│  └──────────┬────────────┘   └──────────┬─────────────────┘  │
│             │                           │                    │
│             │    Redis pub/sub          │                    │
│             │    + HTTP internal API    │                    │
│             └──────────────┬────────────┘                    │
│                            │                                 │
│              ┌─────────────▼──────────────┐                  │
│              │     PostgreSQL + Redis      │                  │
│              └─────────────┬──────────────┘                  │
│                            │                                 │
│           ┌────────────────┼────────────────┐                │
│           ▼                ▼                ▼                │
│     Indicator          Portfolio        News Cache           │
│     Calculator          Manager                              │
│           │                                                  │
│           ▼                                                  │
│     Candidate Selector                                       │
│     (Rule-based — RSI, VI, 상한가 등 1차 필터)               │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────────────────────────────────────────┐        │
│  │                   AI Gateway                     │        │
│  │                                                  │        │
│  │  1순위  Claude API      직접 호출 (anthropic SDK) │        │
│  │         └── Prompt Caching L1(1h) · L2(5m)       │        │
│  │  2순위  Gemini Free     뉴스 요약·보조 분석        │        │
│  │  3순위  DeepSeek Free   Claude 장애 시 폴백        │        │
│  └───────────────────┬──────────────────────────────┘        │
│                      │                                       │
│         ┌────────────▼────────────┐                          │
│         │     Decision Engine     │                          │
│         │  JSON 파싱·신뢰도 검증   │                          │
│         └────────────┬────────────┘                          │
│                      │                                       │
│         ┌────────────▼────────────┐                          │
│         │      Risk Engine        │                          │
│         │      Safety Gate        │                          │
│         └────────────┬────────────┘                          │
│                      │                                       │
│         ┌────────────▼────────────┐                          │
│         │     Order Executor      │                          │
│         │  토스 API 주문 실행      │                          │
│         └────────────┬────────────┘                          │
└──────────────────────┼──────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  Toss Trading API            Discord API
  (주문·시세·계좌)            (알림·명령 수신)
```

---

## 디렉토리 구조

```
TossInvestAI/
├── CLAUDE.md                        # 최상위 컨텍스트 (필독)
├── docs/                            # 상세 설계 문서
│   ├── ARCHITECTURE.md
│   ├── BIN.md
│   ├── DISCORD.md
│   ├── REPORT.md
│   ├── SAFETY.md
│   ├── LOGGING.md
│   ├── FUND_MANAGER.md
│   ├── TOSS_API.md
│   ├── CODING_RULES.md
│   ├── SELF_IMPROVEMENT.md
│   ├── INTERNAL_API.md
│   ├── MONITOR.md
│   └── DEPLOYMENT.md
│
├── .env                             # 비밀 키 (git 커밋 금지)
├── .env.example                     # 환경변수 템플릿
│
├── discord-bot/                     # Discord.js + TypeScript
│   ├── src/
│   │   ├── index.ts                 # 봇 진입점
│   │   ├── config.ts                # 환경변수 로드 (채널 ID 등)
│   │   ├── commands/
│   │   │   ├── status.ts
│   │   │   ├── buy.ts
│   │   │   ├── sell.ts
│   │   │   ├── cancel.ts
│   │   │   ├── stop.ts
│   │   │   ├── resume.ts
│   │   │   ├── report.ts
│   │   │   ├── fund.ts
│   │   │   ├── dryrun.ts
│   │   │   ├── watchlist.ts
│   │   │   ├── backtest.ts
│   │   │   ├── health.ts
│   │   │   └── version.ts
│   │   ├── embeds/                  # Embed 빌더
│   │   │   ├── trade.ts
│   │   │   ├── status.ts
│   │   │   ├── report.ts
│   │   │   └── alert.ts
│   │   ├── events/
│   │   │   └── ready.ts
│   │   └── lib/                     # core 내부 API 통신 (docs/INTERNAL_API.md)
│   │       ├── coreClient.ts        # HTTP 클라이언트 (discord-bot → core 요청)
│   │       └── eventSubscriber.ts   # Redis pubsub:events 구독 (core → discord-bot 알림)
│   ├── package.json
│   └── tsconfig.json
│
├── monitor/                         # Next.js 키오스크 모니터 (docs/MONITOR.md) — 상호작용 없음
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           # 폰트(Noto Sans KR·JetBrains Mono), 뷰포트
│   │   │   ├── page.tsx             # KioskStage + MonitorDashboard 조립
│   │   │   └── api/snapshot/route.ts  # 스냅샷 JSON (현재 목업, 실연동 시 core 프록시)
│   │   ├── components/              # Header·SubStrip·TotalAssetsCard·PnlChart 등 섹션별 컴포넌트
│   │   └── lib/                     # MonitorSnapshot 타입, 목업 데이터, 포맷터
│   └── package.json
│
├── core/                            # Python 트레이딩 코어
│   ├── main.py                      # bin-core.service 진입점 (스케줄러 + 내부 API 기동)
│   ├── config.py                    # 설정 단일 진입점 (pydantic-settings)
│   ├── models.py                    # 공유 도메인 모델 (Order·Decision·GateResult 등)
│   │
│   ├── trading/
│   │   ├── loop.py                  # KR·US 트레이딩 루프 (APScheduler)
│   │   ├── decision.py              # Claude API 직접 호출 진입점
│   │   ├── executor.py              # LIVE/SIMULATION 분기 실행
│   │   ├── reflection.py            # 장 마감 자기평가
│   │   ├── self_improvement.py      # 개선 후보 제안 + 백테스트 게이트 (docs/SELF_IMPROVEMENT.md)
│   │   └── prompts/                 # Claude 시스템 프롬프트 파일
│   │       ├── system_kr.md         # KR 시스템 프롬프트  (L1 캐시 대상)
│   │       ├── system_us.md         # US 시스템 프롬프트  (L1 캐시 대상)
│   │       └── reflection.md
│   │
│   ├── gateway/
│   │   ├── base.py                  # AIGateway 추상 인터페이스
│   │   ├── claude.py                # Claude API 클라이언트 (Prompt Caching 포함)
│   │   ├── gemini.py                # Gemini Free Tier 클라이언트
│   │   └── deepseek.py              # DeepSeek Free Tier 클라이언트
│   │
│   ├── api/                         # discord-bot ↔ core 내부 HTTP API 서버 (docs/INTERNAL_API.md)
│   │   ├── server.py                # aiohttp.web 앱 팩토리 + 인증 미들웨어, 127.0.0.1 바인딩
│   │   └── routes.py                # 엔드포인트 핸들러
│   │
│   ├── toss/
│   │   ├── auth.py                  # OAuth2 토큰 발급·갱신
│   │   ├── client.py                # Rate Limit 처리, 지수 백오프
│   │   ├── market.py                # 시세·캘린더·환율·종목 조회
│   │   ├── account.py               # 계좌·보유주식·매수가능금액
│   │   └── order.py                 # 주문 생성·정정·취소
│   │
│   ├── strategy/
│   │   ├── base.py                  # BaseStrategy 추상 클래스
│   │   ├── backtest.py              # 백테스트 엔진 (1Y·3Y·5Y)
│   │   ├── paper_trading.py         # 모의투자 모드
│   │   ├── kr/
│   │   │   ├── momentum.py
│   │   │   └── mean_reversion.py
│   │   └── us/
│   │       ├── momentum.py
│   │       └── overnight.py
│   │
│   ├── safety/
│   │   └── gate.py                  # Safety Gate (모든 주문의 필수 관문)
│   │
│   ├── fund/
│   │   └── manager.py               # 자금 배분·재투자·API 비용 추적
│   │
│   ├── simulation/
│   │   └── portfolio.py             # 가상 포트폴리오 (SIMULATION 모드 전용)
│   │
│   ├── market_data/
│   │   ├── collector.py             # 시세·뉴스 수집
│   │   ├── indicators.py            # RSI·MACD·EMA·볼린저밴드
│   │   ├── news.py                  # 뉴스 파싱·캐싱 (Gemini 요약)
│   │   └── watchlist.py             # 관심 종목 관리
│   │
│   ├── report/
│   │   ├── generator.py             # 리포트 텍스트 생성
│   │   └── chart.py                 # matplotlib 그래프 생성
│   │
│   ├── db/
│   │   ├── models.py                # SQLAlchemy ORM 모델
│   │   ├── store.py                 # CRUD 함수
│   │   └── backup.py                # 자동 백업·복구
│   │
│   ├── scheduler/
│   │   └── tasks.py                 # APScheduler 태스크 정의
│   │
│   ├── monitoring/
│   │   └── health.py                # CPU·메모리·온도·디스크·네트워크 감시
│   │
│   └── events/
│       ├── calendar.py              # FOMC·CPI·실적발표 이벤트 캘린더
│       └── publisher.py             # Redis pubsub:events 발행 (docs/INTERNAL_API.md)
│
├── logs/
│   ├── trading/                     # YYYY-MM-DD.log (거래 내역)
│   ├── reports/                     # 생성된 리포트 원문·그래프
│   │   └── charts/
│   └── errors/                      # YYYY-MM-DD.log (에러·Safety Gate 거부)
│
├── data/
│   ├── backtest/                    # 백테스트용 과거 데이터
│   └── watchlist.json
│
├── backups/                         # DB 자동 백업
│   ├── daily/
│   ├── weekly/
│   └── monthly/
│
├── deploy/
│   └── systemd/                     # 실제 systemd 유닛 파일 (docs/DEPLOYMENT.md)
│       ├── bin-core.service
│       └── bin-discord.service
│
└── tests/
    ├── test_safety.py
    ├── test_fund_manager.py
    ├── test_toss_client.py
    ├── test_decision.py
    └── test_backtest.py
```

---

## systemd 서비스

실제 유닛 파일은 `deploy/systemd/bin-core.service`·`deploy/systemd/bin-discord.service`를
기준으로 삼는다(이 문서에 별도로 옮겨 적지 않는다) — 배포·설치 절차는
[`docs/DEPLOYMENT.md`](./DEPLOYMENT.md) 참고. `bin-core.service`의 `ExecStart`는
`python3 -m core.main`(스케줄러 + 내부 API 서버를 한 프로세스로 기동)을 사용하며,
`WorkingDirectory`는 저장소 루트다(`core.main`이 `core/` 패키지를 임포트하므로).

---

## DB 스키마

### PostgreSQL

| 테이블 | 설명 |
|--------|------|
| `trades` | 체결된 거래 전체 내역 |
| `orders` | 주문 이력 (미체결 포함, `action`·`quantity`·`price` 포함) |
| `positions` | 현재 보유 포지션 (매수 시 환율 포함) |
| `decisions` | AI 의사결정 히스토리 JSON |
| `paper_trades` | 모의투자 체결 내역 |
| `daily_pnl` | 일별 손익 |
| `api_usage` | Claude API 토큰·비용 기록 |
| `watchlist` | 관심 종목 및 우선순위 |
| `strategy_versions` | 프롬프트·전략 버전 기록 |
| `reflections` | 일일 자기평가 리포트 (`proposed_change` 포함) |
| `market_events` | 시장 이벤트 캘린더 |
| `safety_rejections` | Safety Gate 거부 이력 (`mode` 컬럼 포함) |
| `control_flags` | 긴급 정지 상태 + SIMULATION 시작 시각 (단일 행, id=1) |
| `fund_rebalances` | 주간 자금 재배분 실행 이력 (감사 기록) |
| `simulation_trades` | 시뮬레이션 가상 체결 내역 |
| `simulation_positions` | 시뮬레이션 가상 보유 포지션 |
| `simulation_daily_pnl` | 시뮬레이션 가상 일별 손익 |
| `simulation_portfolio_snapshots` | 시뮬레이션 포트폴리오 스냅샷 |
| `live_portfolio_snapshots` | 실전 포트폴리오 스냅샷 (자산 추이 차트용) |
| `reports` | 정기/즉시 리포트 발행 기록 — 전체 마크다운은 `logs/reports/*.md`에만 남고, 여기는 모니터(`docs/MONITOR.md`) 서브스트립이 쓰는 한 줄 요약만 감사 가능하게 영속화 |

> `daily_pnl`/`simulation_daily_pnl`은 스키마상 존재하지만 실제 쓰기 경로가
> 없다 — 모니터의 일별 손익 차트는 대신 `live_portfolio_snapshots`(또는
> 시뮬레이션은 `simulation_portfolio_snapshots`)의 일별 델타로 계산한다
> (`core/api/monitor_snapshot.py`).

### Redis

| 키 패턴 | TTL | 용도 |
|---------|-----|------|
| `price:{symbol}` | 10s | 현재가 캐시 |
| `candle:{symbol}:{tf}` | 60s | 캔들 데이터 캐시 |
| `news:{symbol}` | 15분 | 뉴스 RSS 피드 캐시 |
| `ratelimit:{group}` | 1s | Toss API Rate Limit 카운터 |
| `ratelimit:peak_last:{group}` | — | 피크 시간대 최소 요청 간격 제어 |
| `token:toss` | 만료 5분 전 갱신 | OAuth2 Access Token |
| `market_open:{market}` | 60s | 장 운영 여부 캐시 |
| `control:flags` | — | 긴급 정지 상태 캐시 (Redis, DB와 함께 갱신) |
| `health:latest` | 5분 | 헬스 모니터링 최신 스냅샷 |
| `pubsub:events` | — | 트레이딩 코어 → Discord 봇 이벤트 |
