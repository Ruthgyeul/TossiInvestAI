# TossInvestAI — 빈(Bin)

Raspberry Pi 5에서 24/7 실행되는 AI 자동 주식 트레이딩 봇.
한국장(KRX)과 미국장(US)을 동시에 운용하며, 모든 상태와 결정을 Discord로 공유한다.

> 코드를 작성하거나 수정하기 전에 [`CLAUDE.md`](./CLAUDE.md)와 `docs/` 문서를 먼저 읽는다.

## 현재 상태

`docs/CODING_RULES.md`의 개발 순서(Phase 1~5) 기준 **코드 구현은 Phase 1~5 전체 완료**.

- Safety Gate(11개 조건)·FundManager(SIMULATION/LIVE 완전 분리, 주간 재배분 감사 기록)
- AI Gateway(Claude 직접 호출 + Prompt Caching, Gemini 뉴스 요약, DeepSeek 폴백)
- 트레이딩 루프(KR·US, 규칙 기반 필터 → Claude 판단), Discord 봇, 리포트(8종 차트 전부 연결)
- 자기평가(Reflection) + 자기개선 파이프라인(개선 후보 제안 → 백테스트 게이트 →
  Discord 승인/반려/롤백, `docs/SELF_IMPROVEMENT.md`)
- 백테스트 엔진(`core/strategy/backtest.py`), 모의투자 신호 검증(`paper_trading.py`)
- US 오버나이트 갭 대응 전략, 무료 RSS 뉴스 소스, 자동 백업/복구, 헬스 모니터링

**남은 것은 코드가 아니라 운영 절차**다 — `docs/SAFETY.md`의 SIMULATION 체크리스트를
통과하고 `SIMULATION=true`로 **최소 2주 이상 실제 리허설**을 거친 뒤에만
`SIMULATION=false`(실전)로 전환한다. 2주 미만이면 `/simulate off` 자체가 코드 레벨에서
거부된다(`core/api/routes.py:post_simulate`). 이후 소액 실거래 1주 + 7일 모니터링까지
문제가 없어야 정식 운용으로 넘어간다(`docs/CODING_RULES.md` Phase 5, 18~20단계).

자기개선 파이프라인은 개선 후보 제안·백테스트 검증·승인/반려/롤백까지 자동화되어
있지만, 실제 `core/trading/prompts/*.md` 프롬프트 문구 수정이나 전략 파라미터 코드
변경은 승인 이후 개발자가 직접 반영한다(에이전트가 코드를 자율 수정하는 루프는
CLAUDE.md 절대 규칙 10에 따라 만들지 않는다).

---

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| Discord 봇 | Discord.js v14 + TypeScript | 24/7 상시 실행, systemd 관리 |
| 트레이딩 코어 | Python 3.11+ (asyncio) | 매매 루프·분석·리포트 |
| AI 결정 | Claude API (anthropic SDK) | 매수/매도 최종 판단, **직접 호출** — 에이전트 프레임워크 미사용 |
| AI 보조 | Gemini Free Tier | 뉴스 요약, 보조 분석 |
| AI 폴백 | DeepSeek Free Tier | Claude 장애 시 대체 |
| DB | PostgreSQL + Redis | 주 데이터 + 캐시/Rate Limit |
| 거래소 | 토스증권 Open API | 주문·시세·계좌 |

하드웨어: Raspberry Pi 5 (8GB RAM) · 256GB SSD · Ubuntu 24.04 LTS.

---

## 디렉토리 구조

```
CLAUDE.md              # 최상위 컨텍스트 (필독)
docs/                   # 상세 설계 문서 (아래 목록 참고)
core/                   # Python 트레이딩 코어
├── main.py              # bin-core.service 진입점 (스케줄러 + 내부 API를 한 프로세스에서 기동)
├── config.py / models.py
├── trading/            # 트레이딩 루프, 규칙 기반 필터→Claude 직접 호출, 실행기, 자기평가·자기개선, 프롬프트
├── gateway/             # Claude·Gemini·DeepSeek 클라이언트
├── api/                 # discord-bot ↔ core 내부 HTTP API 서버
├── toss/                # 토스증권 Open API 클라이언트
├── strategy/            # 전략 베이스·백테스트·모의투자·KR/US 전략(오버나이트 포함)
├── safety/              # Safety Gate
├── fund/                # 자금 배분·API 비용 추적 (LIVE/SIMULATION 완전 분리)
├── simulation/          # 가상 포트폴리오 (SIMULATION 모드)
├── market_data/         # 시세·지표·뉴스·관심종목
├── report/              # 리포트·그래프 생성
├── db/                  # ORM 모델·CRUD·백업·Redis 클라이언트
├── scheduler/           # APScheduler 태스크 (트레이딩 루프·리포트·백업·자기평가·헬스체크)
├── monitoring/          # 헬스 모니터링
└── events/              # 시장 이벤트 캘린더 · Redis pub/sub 발행
discord-bot/            # Discord.js + TypeScript 봇
deploy/systemd/         # 실제 systemd 유닛 파일 (docs/DEPLOYMENT.md 참고)
tests/                  # pytest 단위 테스트
data/ · logs/ · backups/  # 런타임 데이터 (git 추적 제외, 디렉토리만 유지)
```

전체 트리와 systemd 서비스 정의, DB 스키마는 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) 참고.

---

## 문서

| 문서 | 내용 |
|------|------|
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | 시스템 구조, 디렉토리 트리, DB 스키마, systemd |
| [`docs/BIN.md`](./docs/BIN.md) | 빈(Bin) 정체성, 트레이딩 루프, AI Gateway, Prompt Caching |
| [`docs/DISCORD.md`](./docs/DISCORD.md) | 채널 구성, Slash 명령어, Embed 포맷 |
| [`docs/REPORT.md`](./docs/REPORT.md) | 리포트 스케줄(6회/일), 필수 항목, matplotlib 그래프 |
| [`docs/SAFETY.md`](./docs/SAFETY.md) | Safety Gate 11개 조건, 긴급 정지, 하드 금지 사항 |
| [`docs/LOGGING.md`](./docs/LOGGING.md) | 거래 로그 포맷, 에러 로그, DB 백업, 헬스 모니터링 |
| [`docs/FUND_MANAGER.md`](./docs/FUND_MANAGER.md) | 자금 배분, 수익 재배분, API 비용 추적 |
| [`docs/TOSS_API.md`](./docs/TOSS_API.md) | 토스증권 API 전체 스펙, Rate Limit, 에러 코드 |
| [`docs/CODING_RULES.md`](./docs/CODING_RULES.md) | 코딩 컨벤션, 의존성, Prompt Caching 구현, 개발 순서 |
| [`docs/SELF_IMPROVEMENT.md`](./docs/SELF_IMPROVEMENT.md) | 자기개선 루프, 버전 관리·롤백, 배포 승인 절차 |
| [`docs/INTERNAL_API.md`](./docs/INTERNAL_API.md) | discord-bot ↔ core 내부 통신 스펙 (HTTP API, Redis pub/sub) |
| [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) | 라즈베리파이 배포·업데이트·백업·롤백 절차 |

---

## 시작하기

### 요구 사항
- Python 3.11+, Node.js LTS, PostgreSQL, Redis

### 설정
```bash
cp .env.example .env    # 실제 키·계좌 정보 입력 (.env는 git에 커밋하지 않는다)

# 트레이딩 코어
pip install -r requirements.txt

# Discord 봇
cd discord-bot && npm install
```

### 실행
```bash
# 트레이딩 코어 (스케줄러 + 내부 HTTP API, PostgreSQL·Redis 실행 중이어야 함)
python -m core.main

# Discord 봇
cd discord-bot && npm run build && npm start   # 또는 개발 중엔 npm run dev
```
운영 환경 배포·systemd 등록은 [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) 참고.

### 테스트
```bash
# 트레이딩 코어 단위 테스트 (PostgreSQL·Redis 불필요 — DB/Redis 호출은 monkeypatch로 격리)
pip install -r requirements.txt
pytest

# Discord 봇 타입 체크·빌드
cd discord-bot && npm run typecheck && npm run build
```

### 개발 순서
`docs/CODING_RULES.md`의 Phase 1~5(1~17단계)는 코드 구현이 모두 끝났다. 남은 18~20단계는
코드가 아닌 운영 절차다 — 항상 `DRY_RUN=true`로 개발·디버깅을 마친 뒤, `SIMULATION=true`로
최소 2주 이상 실제 리허설(`docs/SAFETY.md` 체크리스트 통과)을 거치고, 이후 소액 실거래
1주 + 7일 모니터링까지 문제없어야 정식 운용으로 전환한다.

---

## 절대 규칙 (요약)

1. 모든 주문은 Safety Gate(`core/safety/gate.py`)를 통과해야 한다
2. `.env`는 절대 git에 커밋하지 않는다
3. `INITIAL_SEED_KRW`는 손익 계산 기준점이므로 변경하지 않는다
4. 미국장 시간은 하드코딩하지 않고 항상 market-calendar API 기준으로 판단한다
5. 규칙 기반으로 처리 가능한 신호는 Claude API를 호출하지 않는다 (비용 절감)
6. 거래 로그는 절대 삭제하지 않는다
7. Discord 메시지는 모두 Embed 형식으로 전송한다
8. 에이전트 프레임워크(LangChain, AutoGen 등)는 사용하지 않는다 — Claude API를 코드에서 직접 호출한다
9. 실전 전환 전 SIMULATION 모드 2주 이상 필수이며, 실전 DB와 시뮬레이션 DB는 절대 혼용하지 않는다

전체 목록은 [`CLAUDE.md`](./CLAUDE.md)의 "절대 규칙" 참고.
