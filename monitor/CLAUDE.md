# CLAUDE.md — monitor (BIN MONITOR 키오스크)

> 이 폴더는 루트 [`CLAUDE.md`](../CLAUDE.md)가 정의하는 빈(Bin) 프로젝트의
> 하위 앱이다. 여기서 작업하기 전에 루트 `CLAUDE.md`와
> [`docs/MONITOR.md`](../docs/MONITOR.md)를 먼저 읽는다. Next.js 관련
> 세부사항은 `@AGENTS.md`도 함께 참고한다.

@AGENTS.md

## 이 앱의 목적

7인치 모니터에 24/7 띄워두는 **읽기 전용 키오스크 디스플레이**다.
트레이딩 코어(`core/`)·Discord 봇(`discord-bot/`)과는 별도의 Next.js
프로젝트이며, 매매를 실행하거나 core에 쓰기 요청을 보내지 않는다 — 오직
상태를 보여주기만 한다.

## 절대 규칙

1. **대시보드(`/`)에는 상호작용 요소를 추가하지 않는다.** 버튼, 링크, 폼,
   클릭/터치 핸들러, 호버 전용 정보 노출 금지. 사용자가 이 화면을 조작할
   일이 없다는 전제로 설계됐다 — 키보드·마우스·터치 없이도 모든 정보가 항상
   보여야 한다. **유일한 예외가 `/auth`** (외부 IP 접속 인증 코드 입력
   화면)다 — 물리적 키오스크와는 다른 용도이므로 여기엔 폼·버튼이 있어도
   된다. 새 상호작용 요소를 추가할 때는 반드시 그게 `/auth` 아래인지
   확인한다.
2. **디자인을 임의로 재해석하지 않는다.** 색상·간격·타이포는
   `claude.ai/design`의 **Bin Monitor.dc.html** 원본 값을 그대로 따른다.
   변경이 필요하면 먼저 디자인 프로젝트를 갱신한 뒤 코드에 반영한다.
   (`/auth`는 원본 디자인에 없는 화면이므로 이 규칙의 적용 대상이 아니다 —
   다만 같은 다크 테마 토큰을 재사용해 시각적 일관성은 유지한다.)
3. **`core`의 내부 API 토큰을 브라우저로 내려보내지 않는다.** 실데이터
   연동 시 `CORE_INTERNAL_API_TOKEN`은 Next.js Route Handler(서버 사이드)
   안에서만 사용한다 (`docs/INTERNAL_API.md`의 인증 규칙과 동일한 원칙).
4. **폴링 실패가 화면을 비우면 안 된다.** `/api/snapshot` 호출이 실패하면
   마지막으로 받은 정상 스냅샷을 계속 표시한다 (`MonitorDashboard.tsx`).
5. **1024×600 고정 캔버스를 유지한다.** 실제 화면 크기가 다르면
   `KioskStage`의 스케일링으로 해결한다 — 컴포넌트 내부에서 반응형
   브레이크포인트를 만들지 않는다. (`/auth`는 이 캔버스 바깥의 별도
   페이지이므로 일반적인 반응형 레이아웃을 써도 된다.)
6. **인증 코드를 로그·에러 메시지·길드 채널에 노출하지 않는다.**
   `src/lib/auth.ts`가 만드는 코드는 Discord DM으로만 전달된다
   (`discord-bot/src/lib/eventSubscriber.ts`의 `logRaw`가 `[REDACTED]`로
   치환하는 이유). 새 로그·에러 응답에 코드 원문을 그대로 싣지 않는다.
7. **원천 차단(`monitor:auth:blocked:{ip}`)에 자동 만료를 넣지 않는다.**
   3회 실패 후 영구 차단은 의도된 동작이다 — TTL을 추가하거나 재시도
   허용 횟수를 자동으로 늘리는 변경은 `docs/MONITOR.md`를 먼저 갱신한다.
8. **`x-forwarded-for`를 무조건 신뢰하지 않는다.** `src/lib/ip.ts`의 로직과
   전제(리버스 프록시가 이 헤더를 덮어써야 안전하다)를 바꿀 때는
   `docs/MONITOR.md`의 "외부 접속 인증 — 보안 전제"를 함께 갱신한다.

## 스택 메모

- 스타일은 Tailwind가 아니라 순수 CSS Modules (`Dashboard.module.css`,
  `AuthGate.module.css`)다. 원본 디자인의 `oklch()` 값·소수점 px 단위를
  정확히 옮기려면 유틸리티 클래스보다 원본 인라인 스타일에 1:1 대응하는
  클래스가 더 안전하다.
- 색상 토큰은 `src/app/globals.css`의 CSS 변수로 정의돼 있다. 새 색을
  추가할 때도 원본 디자인의 `oklch()` 값을 그대로 옮긴다.
- `cursor: none`/`user-select: none` 같은 키오스크 전용 리셋은
  `KioskStage.module.css`의 `.viewport`에만 있다 — `globals.css`에는 두지
  않는다. 전역에 두면 `/auth`에서 커서·텍스트 선택이 안 돼 폼을 쓸 수 없다.
- `src/proxy.ts`는 Next.js 16의 `middleware.ts` → `proxy.ts` 개명 이후
  컨벤션을 따른다. 기본 Node.js 런타임이라 `ioredis`·`node:crypto`를 그대로
  쓸 수 있다 — Edge 런타임 제약(Web Crypto만 가능 등)을 신경 쓸 필요 없다.
