# MONITOR.md — BIN MONITOR 키오스크 디스플레이

> `monitor/`(Next.js) 앱의 설계 근거와 운영 방식을 설명한다. 코드 수준의
> 세부 규칙은 `monitor/CLAUDE.md`, 실행·데이터 연동 절차는 `monitor/README.md`
> 참고 — 여기서 중복 설명하지 않는다.

---

## 목적

7인치 모니터(1024×600)에 24/7 띄워두는 **읽기 전용 대시보드**. 총자산,
KR·US 포지션, AI 매매 판단, 시스템 헬스, Safety Gate 거부 이력, 뉴스,
시장 이벤트 캘린더를 한 화면에서 실시간으로 보여준다. Discord가 알림·명령
채널이라면, 이 화면은 **눈으로 훑는 상시 상태판**이다 (docs/DISCORD.md와
용도가 다르다 — 명령을 받지 않는다).

디자인 원본은 `claude.ai/design`의 **Bin Monitor.dc.html**(1024×600 고정
캔버스)이며, `monitor/`는 이 디자인을 값 그대로(색상 `oklch()`, 간격 px)
옮긴 구현체다. `/auth`(외부 접속 인증 화면)는 같은 디자인 프로젝트의
**Auth Gate.dc.html**을 값 그대로 옮겼다 — 단, 대시보드와 달리 고정
1024×600 캔버스가 아니라 반응형 페이지로 구현했다(아래 "외부 접속 인증"
참고).

---

## 왜 별도 Next.js 프로젝트인가

- `core`(Python)와 `discord-bot`(Node)은 트레이딩 로직·알림을 담당하고,
  `monitor`는 순수 프레젠테이션 계층이다 — 매매를 실행하거나 core에 쓰기
  요청을 보내지 않는다. 별도 저장소로 분리하지 않고 같은 모노레포의
  `/monitor` 폴더에 둔 이유는 같은 라즈베리파이에서 함께 배포·운영되기
  때문이다 (docs/ARCHITECTURE.md 하드웨어 구성과 동일 기기).
- Next.js(App Router)를 선택한 이유: 정적으로 내려줄 화면이지만 실데이터
  연동 시 서버 사이드 Route Handler로 `core`의 내부 API 토큰을 브라우저에
  노출하지 않고 프록시할 수 있어야 한다 (docs/INTERNAL_API.md의 `Bearer`
  토큰·`127.0.0.1` 바인딩 규칙과 동일한 이유). 순수 정적 HTML로는 이 프록시
  계층을 깔끔하게 넣기 어렵다.

---

## 상호작용 없음 — 하드 제약

**대시보드 화면(`/`)**에는 버튼, 링크, 폼, 클릭/터치/호버 핸들러가 없다. 조작이
필요한 동작(주문 승인/거부, `/stop`, `/resume` 등)은 전부 Discord(docs/DISCORD.md)의
몫이다. 대시보드에 상호작용 요소를 추가하는 PR은 이 문서의 설계 의도에 어긋난다.

**유일한 예외는 `/auth`다.** 외부 IP 접속자가 인증 코드를 요청·입력하는 화면으로,
물리적 키오스크 화면(항상 내부 IP로만 접속)과는 다른 용도·다른 사용자를 위한
별개 라우트다 — 아래 "외부 접속 인증" 참고.

---

## 데이터 흐름

```
core (Python, 127.0.0.1:8000)
   │  GET /api/v1/monitor/snapshot  (docs/INTERNAL_API.md, core/api/monitor_snapshot.py)
   │  Authorization: Bearer {CORE_INTERNAL_API_TOKEN}
   ▼
monitor/src/lib/core-client.ts + snapshot-mapper.ts   (server-only)
   │  토큰은 여기서만 사용 — 브라우저로 절대 내려가지 않는다
   ▼
monitor/src/app/api/snapshot/route.ts   (Next.js Route Handler, 서버 사이드)
   │  core 응답 실패 시 502 반환 (스냅샷을 지어내지 않는다)
   ▼
GET /api/snapshot  (같은 오리진, 인증 불필요 — 로컬 키오스크 전용)
   │
   ▼
MonitorDashboard.tsx  (클라이언트, 30초 간격 폴링)
   │  LiveClock은 별도로 매초 KST 틱
   │  폴링 실패 시 마지막 정상 스냅샷 유지, 최초 로드 실패 시 ConnectingScreen → 5초 재시도
   ▼
7인치 모니터
```

`core/api/monitor_snapshot.py`의 `build_monitor_snapshot()`이 여러 내부
소스(포트폴리오, 헬스 스냅샷, 거래·안전장치 로그, `decisions.state_snapshot`,
`reports` 테이블 등)를 하나의 응답으로 집계한다 — 모니터는 여러 엔드포인트를
조합하지 않고 이 하나만 호출한다. 실데이터로 재현할 수 없는 값(토스 인기
종목·공포탐욕지수는 Toss Open API에 해당 엔드포인트가 없다, `docs/TOSS_API.md`)은
`core/market_data/collector.py`가 이미 만들어 둔 근사치를 `state_snapshot`에서
재사용한다 — 별도 API 호출을 추가하지 않는다. 일별 손익 차트는 `daily_pnl`
테이블이 실제로 채워지지 않으므로 포트폴리오 스냅샷의 일별 델타로 대신
계산한다. 개발 중 core 없이 화면만 확인하려면 `MONITOR_USE_MOCK_DATA=true`로
`src/lib/mock-snapshot.ts`의 정적 목업을 쓸 수 있다 — 자세한 흐름은
`monitor/README.md`의 "데이터 연동" 참고.

---

## 화면 구성 (원본 디자인 섹션)

| 영역 | 내용 |
|------|------|
| 헤더 | 로고, LIVE 뱃지, 전략/프롬프트 버전, USD/KRW, KR·US 장 상태, 실시간 시계 |
| 서브 스트립 | 성과(알파·승률·체결률·손익비·샤프지수·연속수익, 5초 회전)·리스크(집중도·변동성·MDD·VaR, 5초 회전)·공포탐욕지수·정기 리포트 요약(마퀴) |
| 총 자산 카드 | 총자산·금일 손익, 현금/KR/US 배분 바, 실현·평가손익, 누적수익률, 시드 금액, 운용일수, 매매 판단 모델, 이번달/금일 API 사용량·비용 |
| 손익 차트 | 상승/하락 바 차트 + 누적·벤치마크·낙폭 오버레이, 평균 수익률·승률 — "전체"/"최근 15일"/"일일"(당일 시간대별) 3개 기간을 5초마다 회전 |
| 시스템 헬스 | 서비스 상태(5초 회전 단일 행), 최근 로그, Safety Gate 거부 이력, 자기평가 요약(세로 마퀴) |
| KR·US 포지션 | 종목별 시장 구분·수량·수익률 |
| AI 매매 판단 | 최근 매매 판단 시각·액션(BUY/SELL/HOLD)·신뢰도 |
| 뉴스 헤드라인 | 감성 태그(호재/주의/악재) + 헤드라인 — 한 번에 하나씩, 가로 스크롤 후 다음 항목으로 회전 |
| 시장 이벤트 | 예정 이벤트 + 위험도(고위험/일반) — 한 번에 하나씩 5초마다 회전 |

성과·리스크 알파는 KOSPI·S&P500 실제 지수 API가 없어(docs/TOSS_API.md) 관심 종목
동일가중 평균 종가를 대체 지수로 쓴다(`core/report/generator.py`의
`_market_composite_series`와 같은 방식). VaR·집중도·변동성·손익비·체결률·연속수익은
전부 이미 쌓인 포트폴리오 스냅샷·거래·Safety Gate 거부 이력에서 계산하며, 계산에
필요한 최소 표본이 없으면(운용 초기 등) 해당 항목을 생략하고 "데이터 수집 중"
플레이스홀더로 대체한다 — 값을 지어내지 않는다.

---

## 화면 크기 대응

원본 디자인은 1024×600 고정 캔버스다. `monitor/src/components/KioskStage.tsx`가
실제 브라우저 뷰포트 크기에 맞춰 이 캔버스를 균등 스케일링(레터박스)한다 —
실제 하드웨어 해상도가 정확히 1024×600이 아니어도 비율이 깨지지 않는다.
컴포넌트 내부에 반응형 브레이크포인트를 추가하지 않는다 (`monitor/CLAUDE.md`
절대 규칙 5).

---

## 외부 접속 인증

물리적 키오스크는 항상 같은 라즈베리파이의 localhost에서 Chromium이 붙으므로
내부 IP로 인식되어 인증 없이 그대로 보인다. 하지만 개발자가 집 밖에서 원격으로
상태를 확인하고 싶을 수도 있어, **내부 IP가 아닌 접속에는 Discord DM으로 받는
1회용 인증 코드**를 요구한다.

### 흐름

1. 외부 IP가 아무 경로로 접속하면 `src/proxy.ts`가 세션 쿠키를 확인하고, 없으면
   `/auth`로 리다이렉트한다.
2. `/auth`가 로드되면(`AuthForm.tsx` 마운트 시점) 자동으로 `POST
   /api/auth/request-code`를 호출해 6자리 코드를 생성해 Redis에 저장(TTL
   `MONITOR_AUTH_CODE_TTL_SECONDS`, 기본 5분)하고, `pubsub:events` 채널
   (docs/INTERNAL_API.md)에 `monitor_auth_code_issued` 이벤트를 발행한다. 코드를
   받지 못했다면 "Discord DM 재전송"으로 같은 요청을 다시 트리거할 수 있다
   (쿨다운 `MONITOR_AUTH_CODE_COOLDOWN_SECONDS`, 기본 30초).
3. discord-bot의 기존 `eventSubscriber.ts`가 이 이벤트를 받아 코드를 **길드 채널이
   아니라 `DISCORD_DEVELOPER_ID`에게 DM으로만** 전송한다
   (`discord-bot/src/embeds/monitorAuth.ts`). `#stock-log`에는 코드 없이
   `[REDACTED]`로만 남는다.
4. 코드를 입력하면 `POST /api/auth/verify-code`가 Redis에 저장된 값과
   타이밍 세이프 비교로 검증한다. 성공하면 요청 IP에 바인딩된 HMAC 서명 쿠키를
   발급하고(`MONITOR_SESSION_TTL_SECONDS`, 기본 12시간), 실패하면 그 IP의 시도
   횟수를 늘린다.
5. 시도 횟수가 `MONITOR_AUTH_MAX_ATTEMPTS`(기본 3회)에 도달하면 그 IP를
   **영구 차단**한다 — TTL 없이 `monitor:auth:blocked:{ip}`를 Redis에 남기므로
   자동 만료되지 않고, 이후로는 `/auth`·`/api/auth/*`를 포함한 모든 요청이
   403이다. 해제는 운영자가 수동으로 `redis-cli DEL monitor:auth:blocked:<ip>`를
   실행해야만 한다.

### monitor가 core·discord-bot과 연결되는 지점

- **Redis**: `monitor`는 이제 `core`·`discord-bot`과 같은 Redis 인스턴스에
  직접 연결하는 세 번째 서비스다 (`REDIS_URL`, `src/lib/redis.ts`). 코드·시도
  횟수·차단 상태는 모두 `monitor:auth:*` 키 아래에 있다 — `core`의 트레이딩
  데이터와 네임스페이스가 겹치지 않는다.
- **`pubsub:events`**: 지금까지 이 채널은 `core`만 발행하고 discord-bot만
  구독했다 (docs/INTERNAL_API.md). `monitor_auth_code_issued`부터는 `monitor`도
  같은 채널에 발행하는 두 번째 publisher다. `core/events/publisher.py`의
  `EventType` Literal은 core가 이 이벤트를 발행할 일이 없으므로 건드리지
  않았다 — discord-bot의 TS `PubSubEvent` 타입에만 이 이벤트를 추가했다.
- **discord-bot이 켜져 있지 않으면 코드 발급 자체가 무의미해진다** — DM을 보낼
  주체가 없기 때문이다. `bin-discord.service`가 죽어 있는 동안에는 외부 접속
  인증이 사실상 막힌다는 뜻이며, 이는 의도된 fail-closed 동작이다(코드를 우회해
  통과시키는 폴백은 두지 않는다).

### 보안 전제 — 반드시 읽는다

- **`x-forwarded-for`/`x-real-ip`는 `server.js`가 신뢰 여부를 판별한 뒤에만
  들어온다.** Next.js Route Handler·`proxy.ts`는 원본 TCP 소켓 주소에 접근할
  방법이 없다(`NextRequest`가 이를 노출하지 않는다) — 그래서 `monitor/server.js`가
  Next에 요청을 넘기기 **전에**, `req.socket.remoteAddress`(위조 불가능한 실제
  접속 IP)를 직접 확인한다. 그 주소가 루프백(같은 라즈베리파이)이거나
  `MONITOR_TRUSTED_PROXY_CIDRS`에 등록된 리버스 프록시가 아니면, 클라이언트가
  보낸 `x-forwarded-for`/`x-real-ip` 값을 버리고 실제 접속 IP로 강제 치환한다.
  이 덕분에 리버스 프록시 없이 라즈베리파이를 인터넷에 직접 노출해도, 공격자가
  헤더를 위조해 "내부 IP"로 위장하는 것은 더 이상 통하지 않는다 — 신뢰 여부가
  서버 소켓 수준에서 이미 결정되기 때문이다. `src/lib/ip.ts`의 `getClientIp`는
  이 전제 위에서만 안전하다(헤더를 그 자체로 신뢰하지 않는다). 리버스 프록시를
  별도 장비에 둔다면(예: 다른 서버의 nginx) 그 장비의 주소를
  `MONITOR_TRUSTED_PROXY_CIDRS`에 등록해야 그 프록시가 설정한 값이 통과된다
  (`monitor/README.md` "외부 접속 인증" 참고).
- **세션 쿠키는 `Secure`(HTTPS 전용)로 설정된다** — TLS 없이 평문으로 세션이
  오가는 것을 막기 위한 의도된 제약이다. 리버스 프록시가 TLS를 종단하지 않으면
  외부 접속에서 로그인 상태가 유지되지 않는다.
- **세션은 요청 IP에 바인딩된다** — 쿠키가 유출돼도 다른 IP에서는 재사용할 수
  없다. 대신 모바일 회선처럼 IP가 자주 바뀌면 재인증이 필요할 수 있다.
- **원천 차단은 자동으로 풀리지 않는다.** 3회 실패가 영구적인 이유는 무차별
  대입을 원천 봉쇄하기 위해서다 — 이 정책을 완화하는 변경(자동 만료, 횟수
  상향 등)은 이 문서를 먼저 갱신한 뒤에 한다.
- **IPv6 시도 횟수·차단은 /64 단위로 묶인다.** ISP가 가정용 회선 하나에 보통
  /64 이상을 통째로 위임하므로, 주소 전체 문자열로 카운트하면 공격자가 같은
  /64 안에서 주소를 바꿔가며 매 시도마다 새로운 3회 기회를 얻어 영구 차단을
  무력화할 수 있었다. `src/lib/ip.ts`의 `rateLimitBucket()`이 IPv6 주소를 /64
  접두사로 잘라 시도 횟수·쿨다운·차단 키를 묶는다(IPv4는 그대로 둔다 — 공인
  IPv4를 여러 개 확보하는 건 현실적으로 어렵다). 세션 바인딩(`signSession`)은
  이 버킷팅의 영향을 받지 않는다 — 도난당한 쿠키의 재사용을 막는 게 목적이라
  IP 전체 문자열을 그대로 유지한다.

환경변수 전체 목록과 로컬 실행 방법은 `monitor/README.md`의 "외부 접속 인증"·
"실행" 참고.

---

## 키오스크 배포

라즈베리파이에서 Chromium을 `--kiosk` 모드로 자동 기동한다. 구체적인 명령과
systemd 예시는 `monitor/README.md`의 "키오스크 배포" 참고. 전체 시스템
배포·백업·롤백 절차는 `docs/DEPLOYMENT.md`를 따른다 — `monitor`도 같은
git pull → 재빌드 → 서비스 재시작 흐름에 포함시킨다.
