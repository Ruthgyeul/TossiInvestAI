# monitor — BIN MONITOR 키오스크 디스플레이

7인치 모니터(1024×600)에 24/7 띄워두는 **읽기 전용 키오스크 대시보드**.
빈(Bin) 트레이딩 봇의 총자산·포지션·AI 매매 판단·시스템 헬스·뉴스를 한 화면에 보여준다.

> **상호작용 요소 없음.** 버튼·링크·클릭 핸들러를 추가하지 않는다 — 이 화면은
> 오직 실시간 정보 확인용이다. 유일한 예외는 `/auth`(외부 접속 인증 코드 입력
> 화면)로, 물리적 키오스크 화면과는 별개의 용도다 — 아래 "외부 접속 인증" 참고.
> 루트 [`CLAUDE.md`](../CLAUDE.md)와 [`docs/MONITOR.md`](../docs/MONITOR.md)를
> 먼저 읽는다.

디자인 원본: `claude.ai/design`의 **Bin Monitor.dc.html** (1024×600 고정 캔버스).

## 기술 스택

| 항목 | 선택 |
|------|------|
| 프레임워크 | Next.js (App Router) + TypeScript |
| 스타일 | CSS Modules — 원본 디자인의 정확한 `oklch()` 값·px 단위를 그대로 옮기기 위해 Tailwind 대신 순수 CSS 사용 |
| 폰트 | `next/font/google` — Noto Sans KR, JetBrains Mono (빌드 시 자체 호스팅, 런타임에 외부 요청 없음) |
| 데이터 | `GET /api/snapshot` — 현재는 목업(`src/lib/mock-snapshot.ts`), 실데이터 연동은 아래 "데이터 연동" 참고 |
| 외부 접속 인증 | `src/proxy.ts` (Next.js Proxy, Node.js 런타임) + Redis — 아래 "외부 접속 인증" 참고 |

## 디렉토리 구조

```
monitor/
├── src/
│   ├── proxy.ts               # 내부/외부 IP 판별 + 인증 게이트 (Next.js Proxy, Node 런타임)
│   ├── app/
│   │   ├── layout.tsx        # 폰트, 뷰포트(줌 비활성화), 메타데이터
│   │   ├── page.tsx           # KioskStage + MonitorDashboard 조립
│   │   ├── globals.css        # 디자인 토큰(oklch 색상 변수)
│   │   ├── api/
│   │   │   ├── snapshot/route.ts       # 스냅샷 JSON 엔드포인트 (현재 목업)
│   │   │   └── auth/
│   │   │       ├── request-code/route.ts  # 인증 코드 발급 (Redis 저장 + Discord DM 발행)
│   │   │       └── verify-code/route.ts   # 인증 코드 검증 + 세션 쿠키 발급
│   │   └── auth/
│   │       ├── page.tsx       # /auth 페이지 (뷰포트 줌 복원)
│   │       ├── AuthForm.tsx   # 코드 요청·입력 폼 — 유일한 상호작용 화면
│   │       └── AuthGate.module.css
│   ├── components/
│   │   ├── KioskStage.tsx     # 1024x600 캔버스를 실제 화면 크기에 맞춰 스케일링 (cursor:none 등 키오스크 전용 리셋 포함)
│   │   ├── MonitorDashboard.tsx  # 30초 간격 폴링 + 전체 조립
│   │   ├── Dashboard.module.css  # 전체 대시보드 스타일 (섹션별 클래스)
│   │   ├── LiveClock.tsx      # 1초마다 틱 (KST 고정)
│   │   └── Header.tsx / SubStrip.tsx / TotalAssetsCard.tsx / PnlChart.tsx /
│   │       SystemHealthPanel.tsx / PositionsPanel.tsx / AiDecisionsPanel.tsx /
│   │       NewsPanel.tsx / EventCalendarPanel.tsx
│   └── lib/
│       ├── types.ts           # MonitorSnapshot 및 하위 타입
│       ├── mock-snapshot.ts   # 목업 데이터 (디자인 원본 값과 동일)
│       ├── format.ts          # KRW/퍼센트 포맷터, 부호 기반 색상 클래스 선택
│       ├── ip.ts               # 내부 IP 판별, x-forwarded-for 파싱
│       ├── redis.ts            # ioredis 싱글턴 (core·discord-bot과 동일 인스턴스)
│       └── auth.ts             # 인증 코드 발급/검증, 시도 횟수, 영구 차단, 세션 서명
```

## 실행

```bash
cp .env.example .env
# MONITOR_SESSION_SECRET는 `openssl rand -base64 32`로 생성해 채운다 (.env는 git에 커밋하지 않는다)

npm install
npm run dev      # http://localhost:3000
npm run build && npm start   # 프로덕션 빌드
npm run lint
```

## 데이터 연동

지금은 `src/lib/mock-snapshot.ts`가 정적 목업을 반환하고, `MonitorDashboard`가
`/api/snapshot`을 30초마다 폴링해 화면을 갱신한다 (초 단위 시계는 `LiveClock`이
별도로 매초 틱). 실데이터로 전환하려면:

1. `core`의 내부 API(`docs/INTERNAL_API.md`)에 이 대시보드 전용 읽기 스냅샷
   엔드포인트를 추가하거나, `/api/v1/status`·`/fund`·`/health` 등 기존
   엔드포인트를 조합한다.
2. `core`의 HTTP 서버는 `127.0.0.1`에만 바인딩하고 `Bearer` 토큰이 필요하다
   (`CORE_INTERNAL_API_TOKEN`). 이 토큰은 **절대 브라우저로 내려보내지 않는다** —
   `src/app/api/snapshot/route.ts`(Next.js Route Handler, 서버 사이드)에서만
   `core`를 호출하고, 브라우저는 이 프록시 엔드포인트만 본다.
3. `route.ts`의 `getMockSnapshot()` 호출을 실제 `fetch()` 호출로 교체하고,
   `MonitorSnapshot` 타입에 맞게 응답을 매핑한다.
4. 모니터는 트레이딩 코어와 같은 라즈베리파이에서 실행된다(`docs/DEPLOYMENT.md`).
   물리적 키오스크 화면은 항상 로컬 네트워크로 붙지만, 외부에서 원격으로 상태를
   확인하고 싶을 수도 있어 아래 "외부 접속 인증"으로 그 경로를 열어둔다.

## 외부 접속 인증

내부 IP(사설 대역·루프백, `MONITOR_TRUSTED_CIDRS`로 추가 가능)에서 접속하면
그대로 대시보드가 보인다. **그 외의 IP**는 `/auth`로 리다이렉트되어 인증 코드를
입력해야 한다. 전체 흐름은 `src/proxy.ts`가 모든 요청 앞단에서 판단한다
(Next.js 16부터 `middleware.ts`가 `proxy.ts`로 이름이 바뀌었고 기본적으로
Node.js 런타임에서 실행된다 — `ioredis`·`node:crypto`를 그대로 쓸 수 있는 이유다).

```
외부 IP 접속
  → proxy.ts: 차단된 IP인가? (Redis monitor:auth:blocked:{ip}) → 403
  → 세션 쿠키가 유효한가? → 통과
  → /auth로 리다이렉트
       → "인증 코드 요청" → POST /api/auth/request-code
            → Redis에 6자리 코드 저장(TTL) + pubsub:events에 monitor_auth_code_issued 발행
            → discord-bot이 구독 중이던 그 채널에서 이벤트를 받아 DISCORD_DEVELOPER_ID에게 DM
       → 코드 입력 → POST /api/auth/verify-code
            → 일치하면 IP에 바인딩된 서명 쿠키 발급, 불일치하면 시도 횟수 +1
            → MONITOR_AUTH_MAX_ATTEMPTS(기본 3회) 도달 시 그 IP를 영구 차단
```

핵심 설계는 `docs/MONITOR.md`의 "외부 접속 인증" 참고. 요약하면:

- **원천 차단은 수동으로만 해제한다.** `redis-cli DEL monitor:auth:blocked:<ip>` —
  자동 만료 없음. 이건 의도된 동작이다.
- **코드는 Discord DM으로만 전달된다.** 길드 채널 로그(`#stock-log`)에는 코드가
  아니라 `[REDACTED]`로 남는다 (`discord-bot/src/lib/eventSubscriber.ts`).
- **`x-forwarded-for` 신뢰 모델**: Next.js는 이 헤더가 없을 때만 실제 소켓 IP로
  채워 넣는다. 리버스 프록시 없이 인터넷에 직접 노출하면 클라이언트가 이 헤더를
  위조해 "내부 IP"로 위장할 수 있다 — 외부에 노출할 계획이라면 반드시 신뢰할 수
  있는 리버스 프록시(nginx 등) 뒤에 두고, 프록시가 클라이언트가 보낸 값을 버리고
  실제 연결 IP로 이 헤더를 덮어쓰도록 설정한다.
- **쿠키는 HTTPS 전제(`Secure`)로 설정된다.** 리버스 프록시가 TLS를 종단하지
  않으면 외부 접속에서 세션 쿠키가 저장되지 않는다 (의도된 안전장치 — 평문으로
  세션이 오가는 걸 막는다). `localhost`는 브라우저가 예외로 허용하므로 로컬
  개발에는 영향이 없다.

## 키오스크 배포 (7인치 모니터)

서버는 `deploy/systemd/bin-monitor.service`로 부팅 시 자동 실행한다:

```bash
sudo cp deploy/systemd/bin-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bin-monitor.service
```

그 앞에서 라즈베리파이의 Chromium을 kiosk 모드로 띄워 화면에 표시한다:

```bash
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --check-for-update-interval=31536000 \
  http://localhost:3000
```

물리적 키오스크는 항상 로컬(127.0.0.1/LAN)에서 접속하므로 내부 IP로 인식되어
`/auth` 인증을 절대 거치지 않는다. 화면이 정확히 1024×600이 아니어도
`KioskStage`가 원본 비율을 유지한 채 레터박스로 맞춰 그리므로 레이아웃이
찌그러지지 않는다. 전체 시스템 배포·백업·롤백 절차는
[`docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md) 참고.

## 디자인 충실도

- 색상은 디자인 원본의 `oklch()` 값을 그대로 CSS 변수로 옮겼다
  (`src/app/globals.css`) — 임의로 팔레트를 재해석하지 않았다.
- 레이아웃은 4열 그리드(`1.1fr 1fr 1fr 1.3fr` × `1.2fr 0.8fr`)와 하단
  2열 스트립까지 원본 인라인 스타일의 px 값을 그대로 옮겼다.
- 원본 디자인에는 있던 "차트 기간(14일/30일/전체) 선택" 같은 편집 가능한
  prop은 키오스크에 상호작용 요소가 없어야 하므로 구현하지 않았고, 기본값
  "전체"로 고정했다.
