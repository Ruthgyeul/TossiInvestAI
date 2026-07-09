# INTERNAL_API.md — discord-bot ↔ core 내부 통신

> discord-bot과 core가 서로를 호출하는 유일한 스펙 문서다.
> `docs/DISCORD.md`의 "Discord 봇은 Python 트레이딩 코어와 Redis pub/sub 또는
> HTTP 내부 API로 통신한다"는 한 줄을 여기서 구체화한다.
> `core/api/server.py`·`routes.py`, `discord-bot/src/lib/coreClient.ts`·
> `eventSubscriber.ts`에 Phase 4에서 실제 구현이 완료되었다 (docs/CODING_RULES.md 개발 순서).
> `monitor/`(키오스크)도 같은 HTTP 내부 API의 세 번째 클라이언트다 — `GET
> /api/v1/monitor/snapshot` 한 엔드포인트만 서버 사이드로 호출한다(docs/MONITOR.md).
> discord-bot처럼 Redis pub/sub을 구독하지는 않고, 대신 인증 코드 발급 시
> `pubsub:events`에 발행은 한다(아래 "Redis pub/sub 이벤트"의 `monitor_auth_code_issued`).

---

## 두 채널 개요

| 채널 | 방향 | 전송 방식 | 용도 |
|------|------|-----------|------|
| 개발자 명령 → 응답 | discord-bot → core → discord-bot | HTTP 내부 API | 동기 요청/응답 (`/status`, `/buy` 등) |
| 트레이딩 이벤트 → 알림 | core → discord-bot | Redis `pubsub:events` | 단방향 푸시 (체결, Safety Gate 거부, 헬스 경고, 리포트 완료) |

원칙: 개발자가 Discord에서 무언가를 **요청**하면 HTTP, core가 무언가를
**통지**하면 Redis pub/sub. 하나의 명령이 둘 다를 쓸 수도 있다 (예: `/report`는
HTTP로 작업을 접수하고, 완료는 pub/sub 이벤트로 알린다 — 아래 "동기 vs 지연 응답" 참고).

---

## 인증 및 네트워크 격리

- discord-bot의 모든 HTTP 요청에 `Authorization: Bearer {CORE_INTERNAL_API_TOKEN}`
  헤더를 포함한다 (`discord-bot/src/config.ts`의 `config.core.apiToken`).
- core의 HTTP 서버는 **`127.0.0.1`에만 바인딩**한다. discord-bot과 core는 같은
  라즈베리파이에서 실행되므로 외부에 노출할 필요가 없다 — 이 문서의 하드 규칙이다.
- 토큰이 없거나 일치하지 않으면 `401 {"error": "unauthorized"}`. 다른 토큰으로
  재시도하지 않고, discord-bot은 즉시 일반 에러 임베드로 실패를 알린다.
- 구현은 `aiohttp.web`을 사용한다 — `requirements.txt`에 이미 `aiohttp>=3.9`가
  있어 새 의존성 추가 없이 가능하다 (FastAPI/uvicorn 등은 도입하지 않는다).

---

## 요청/응답 공통 규칙

- 모든 요청/응답 바디는 JSON.
- 모든 응답은 `mode: "LIVE" | "SIMULATION" | "DRY_RUN"` 필드를 포함한다
  (`core/models.py`의 `Mode`와 동일) — discord-bot이 이 값으로 시뮬레이션
  뱃지(`🟡 [시뮬레이션]`, docs/SAFETY.md)를 붙일지 판단한다.
- **Safety Gate 거부는 HTTP 에러가 아니다.** `200 OK` + `GateResult` 형태로
  응답한다: `{"approved": false, "reason": "..."}`. 거부는 정상적인 비즈니스
  결과이지 프로토콜 실패가 아니기 때문이다. 4xx/5xx는 인증 실패·입력값 오류·
  서버 크래시에만 사용한다.
- Safety Gate 거부는 **HTTP 응답과 무관하게 항상** `safety_rejection` pub/sub
  이벤트로 `#stock-error`에도 전달된다 — 수동 `/buy`·`/sell`이든 자동 매매 루프든
  동일하다 (docs/SAFETY.md "거부 처리 흐름"과 일관).

---

## 동기 vs 지연 응답

Discord 인터랙션은 3초 내 ACK가 필요하다. 아래 두 명령만 즉시 결과를 만들 수
없으므로 지연 응답 패턴을 쓴다.

- `/report`, `/backtest` → 즉시 `202 {"jobId": "..."}` 반환. discord-bot은
  `interaction.deferReply()`로 응답을 미룬다. core는 작업 완료 시 동일한
  `jobId`를 `correlation_id`로 실은 `report_ready`/`backtest_complete` pub/sub
  이벤트를 발행하고, discord-bot은 이를 받아 해당 인터랙션을 `editReply()`로
  마무리한다.
- 나머지 명령(`/status`, `/holdings`, `/orders`, `/buy`, `/sell`, `/cancel`,
  `/stop`, `/resume`, `/simulate`, `/dryrun`, `/simstatus`, `/fund`, `/apicost`,
  `/watchlist`, `/health`, `/version`과 그 하위 명령)은 동기 응답으로 충분하다.

---

## 엔드포인트

| Method & Path | 슬래시 명령어 | 명령어 파일 | 요청 바디 | 응답 바디 |
|---|---|---|---|---|
| `GET /api/v1/status?market=KR\|US` | `/status`, `/status kr\|us` | `status.ts` | — | `{ live: PortfolioStatus \| null, simulation: PortfolioStatus }` (`embeds/status.ts`의 `PortfolioStatus`) |
| `GET /api/v1/holdings?market=KR\|US` | `/holdings` | `status.ts` | — | `{ holdings: Holding[] }` (`embeds/status.ts`의 `Holding`) |
| `GET /api/v1/orders` | `/orders` | `status.ts` | — | `{ orders: { orderId, symbol, market, action, quantity, price, status, createdAt }[] }` (`core/db/models.py`의 `Order` 모델과 매칭) |
| `POST /api/v1/orders/buy` | `/buy` | `buy.ts` | `{ symbol, quantity, price? }` | `{ approved, reason?, orderId?, fillPrice? }` |
| `POST /api/v1/orders/sell` | `/sell` | `sell.ts` | `{ symbol, quantity, price? }` | `{ approved, reason?, orderId?, fillPrice? }` |
| `POST /api/v1/orders/{orderId}/cancel` | `/cancel` | `cancel.ts` | — | `{ success: boolean, reason?: string }` |
| `POST /api/v1/control/stop` | `/stop`, `/stop kr\|us` | `stop.ts` | `{ market?: "KR"\|"US" }` | `{ success: boolean, emergencyStop: boolean, krStop: boolean, usStop: boolean, cancelledOrders: string[] }` |
| `POST /api/v1/control/resume` | `/resume` | `resume.ts` | `{}` | `{ success: boolean }` — Discord 쪽에서 버튼 클릭으로 개발자 확인을 받은 뒤에만 호출한다 (docs/SAFETY.md) |
| `POST /api/v1/control/simulate` | `/simulate on\|off` | `dryrun.ts` | `{ state: "on"\|"off" }` | `{ success: boolean, simulation: boolean, reason?: string }` — `off`는 SIMULATION 최소 2주 미달 시 `success: false`로 거부 (docs/SAFETY.md) |
| `POST /api/v1/control/dryrun` | `/dryrun on\|off` | `dryrun.ts` | `{ state: "on"\|"off" }` | `{ success: boolean, dryRun: boolean }` |
| `GET /api/v1/simstatus` | `/simstatus` | `dryrun.ts` | — | 기간·가상 시드/총자산·수익률·MDD·샤프·거래횟수·승률·평균보유일·거부횟수·API비용 (docs/FUND_MANAGER.md `/simstatus` 예시와 동일 필드) |
| `POST /api/v1/reports/generate` | `/report`, `/report kr\|us` | `report.ts` | `{ market?: "KR"\|"US"\|"ALL" }` | `202 { jobId }` → 이후 `report_ready` 이벤트로 `ReportEmbedData`(`embeds/report.ts`) 전달 |
| `GET /api/v1/fund` | `/fund` | `fund.ts` | — | `{ operatingFundsKrw, cashBufferKrw, cumulativeReturnPct, positionRatios: {symbol, ratio}[] }` (docs/FUND_MANAGER.md `FundManager` 메서드와 매칭) |
| `GET /api/v1/fund/apicost` | `/apicost` | `fund.ts` | — | `{ monthCostKrw, monthCostUsd, callCount }` |
| `GET /api/v1/watchlist?market=` | `/watchlist` | `watchlist.ts` | — | `{ items: { symbol, market, priority }[] }` |
| `POST /api/v1/watchlist` | `/watchlist add` | `watchlist.ts` | `{ symbol, market }` | `{ success: boolean }` |
| `DELETE /api/v1/watchlist/{symbol}` | `/watchlist remove` | `watchlist.ts` | — | `{ success: boolean }` |
| `POST /api/v1/backtest` | `/backtest` | `backtest.ts` | `{ strategy, period: "1Y"\|"3Y"\|"5Y" }` | `202 { jobId }` → 이후 `backtest_complete` 이벤트로 `BacktestResult`(`core/strategy/backtest.py`: `win_rate, avg_return, mdd, sharpe_ratio, profit_factor`) 전달 |
| `GET /api/v1/health` | `/health` | `health.ts` | — | `HealthSnapshot`(`core/monitoring/health.py`: `cpu_pct, memory_pct, disk_pct, temp_c, toss_api_reachable, collected_at`) |
| `GET /api/v1/monitor/snapshot` | (없음 — discord-bot이 아니라 `monitor/`가 호출) | `core/api/monitor_snapshot.py` | — | 키오스크 대시보드 전체 스냅샷 — `header`·`subStrip`·`totalAssets`·`chart`·`systemHealth`·`positions`·`aiDecisions`·`news`·`events` (docs/MONITOR.md "데이터 흐름") |
| `GET /api/v1/version` | `/version` | `version.ts` | — | `{ strategyVersion, promptVersion, deployedAt }` — 승인·배포된(approved_by not null) 최신 레코드만 (`strategy_versions` 테이블) |
| `GET /api/v1/version/candidates` | `/version candidates` | `version.ts` | — | `{ candidates: VersionCandidate[] }` — 승인 대기 중(approved_by null) 후보 (docs/SELF_IMPROVEMENT.md) |
| `POST /api/v1/version/{id}/approve` | `/version approve` | `version.ts` | `{ approvedBy }` | `{ success, reason? }` — 후보를 승인·배포 상태로 전환 |
| `POST /api/v1/version/{id}/reject` | `/version reject` | `version.ts` | — | `{ success, reason? }` — 승인 대기 후보를 폐기(이미 배포된 버전은 거부) |
| `POST /api/v1/version/rollback` | `/version rollback` | `version.ts` | `{ strategyVersion, approvedBy }` | `{ success, reason? }` — 과거 배포 이력이 있는 버전을 새 배포로 재기록 |

**참고**: `/buy`·`/sell`은 `market` 옵션이 없다(`buy.ts`/`sell.ts`). core가
심볼 형식으로 KR/US를 판별한다 — 숫자 종목코드는 KR, 알파벳 티커는 US.

**참고**: `/health`는 매 호출마다 새로 수집하지 않는다. `core/monitoring/health.py`가
5분마다 수집한 `HealthSnapshot`을 Redis 키 `health:latest`에 써 두고, 이 엔드포인트는
그 값을 읽기만 한다. (`health:latest`는 이 문서에서 새로 정의하는 키이며,
`docs/ARCHITECTURE.md`의 Redis 표 갱신은 이번 범위에 포함하지 않는다.)

---

## Redis pub/sub 이벤트

단일 채널 `pubsub:events` (docs/ARCHITECTURE.md Redis 표의 기존 키와 동일).
모든 이벤트는 아래 envelope를 따르고 `payload`만 `event_type`별로 다르다.

```json
{
  "event_type": "trade_executed | safety_rejection | emergency_stop | health_alert | report_ready | backtest_complete | status_update | reflection_ready | news_summary | version_candidate_ready | monitor_auth_code_issued",
  "mode": "LIVE | SIMULATION | DRY_RUN",
  "market": "KR | US | null",
  "correlation_id": "report_ready/backtest_complete에서만 사용, 그 외 null",
  "published_at": "ISO8601",
  "payload": { "...": "event_type별로 다름, embeds/*.ts 인터페이스와 매칭" }
}
```

| event_type | Embed 빌더 | Discord 채널 |
|---|---|---|
| `trade_executed` | `buildBuyEmbed` / `buildSellEmbed` (`embeds/trade.ts`, payload = `TradeEmbedData`) | `#stock-buy` / `#stock-sell` (action에 따라) |
| `safety_rejection` | `buildSafetyRejectionEmbed` (`embeds/alert.ts`) | `#stock-error` |
| `emergency_stop` | `buildEmergencyStopEmbed` (`embeds/alert.ts`) | `#stock-system` |
| `health_alert` | `buildHealthAlertEmbed` (`embeds/alert.ts`) | `#stock-error` |
| `report_ready` | `buildReportEmbed` (`embeds/report.ts`, payload = `ReportEmbedData`) | `#stock-analyze` — 또는 `correlation_id`가 일치하는 `/report` 인터랙션을 edit |
| `backtest_complete` | 전용 Embed 없음 — `correlation_id`로 `/backtest` 인터랙션을 edit | (해당 인터랙션) |
| `status_update` | `buildStatusEmbed` (`embeds/status.ts`) | `#status` 고정 메시지 edit (docs/DISCORD.md "지속 수정" 규칙) |
| `reflection_ready` | `buildReflectionEmbed` (`embeds/alert.ts`, payload = `{market, contentMd}`) | `#stock-system` |
| `news_summary` | `buildNewsEmbed` (`embeds/news.ts`, payload = `{symbol, summary}`) | `#stock-news` — `core/market_data/collector.py`가 뉴스 요약 수집마다 발행 |
| `version_candidate_ready` | 전용 Embed(`eventSubscriber.ts` 내 인라인) | `#stock-system` — `core/trading/self_improvement.py`가 백테스트 통과한 후보 제안 시 발행, `payload = {id, market, strategyVersion, changeSummary, backtestResult}` |
| `monitor_auth_code_issued` | `buildMonitorAuthCodeEmbed` (`embeds/monitorAuth.ts`) | **DM** (`DISCORD_DEVELOPER_ID`), 채널이 아님 — `monitor/src/lib/auth.ts`가 외부 IP 접속 인증 코드 발급 시 발행, `payload = {code, ip, expiresInSeconds}` (docs/MONITOR.md "외부 접속 인증") |

**참고**: `monitor_auth_code_issued`는 이 채널의 유일한 non-`core` 발행자다 —
`monitor`가 `core`·`discord-bot`과 동일한 Redis에 직접 연결해 발행한다. `mode`는
`"SYSTEM"`으로 채워지는데, 이건 트레이딩 모드가 아니라서 core의
`core/models.py` `Mode`에는 없고 discord-bot 쪽 TS 타입에도 실제로는 추가하지
않았다 — `JSON.parse(...) as PubSubEvent`가 unchecked assertion이라 타입
검사를 통과하며, 이 이벤트의 핸들러(`handleMonitorAuthCode`)만 `event.mode`를
읽는다. 이 이벤트는 `#stock-log`에도 기록되지만 `code` 필드는 `[REDACTED]`로
치환된다 — 인증 코드가 길드 채널에 노출되면 안 되기 때문이다.

---

## 에러 처리 / 타임아웃

- 동기 엔드포인트: discord-bot 클라이언트 타임아웃 5초 권장. 타임아웃 또는
  `ECONNREFUSED`(core 다운/재시작 중)면 일반 에러 임베드로 응답하고
  (Safety Gate 거부 임베드와는 다른 것) `#stock-log`에 기록한다.
- 지연 응답: 소프트 타임아웃(리포트 60초, 백테스트 5분) 경과 시 "작업이
  진행 중입니다, 완료되면 알려드립니다"로 edit하고 pub/sub 이벤트를 계속 대기한다
  — 포기하지 않는다.
