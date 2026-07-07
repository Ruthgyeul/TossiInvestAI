# SAFETY.md — Safety Gate

---

## 원칙

> **모든 주문은 `core/safety/gate.py`의 `SafetyGate.check()`를 반드시 통과해야 한다.**
> 수동 명령·백테스트를 포함한 어떠한 경로도 Safety Gate를 우회할 수 없다.

---

## 운영 모드 3단계

세 가지 모드는 완전히 독립된 플래그로 동작한다.

| 모드 | DRY_RUN | SIMULATION | 설명 |
|------|---------|------------|------|
| **실전** | false | false | 실제 주문 실행, 실제 자금 운용 |
| **시뮬레이션** | false | true | 실제와 100% 동일하게 동작, 주문만 가상 체결 |
| **개발** | true | any | 최소 로그, 임시 테스트용 |

### SIMULATION 모드 상세

`SIMULATION=true` 는 실전 투입 전 충분한 데이터를 쌓기 위한 **실전 동일 리허설** 모드다.

- AI 판단, Safety Gate 검증, 수익률 계산, Discord 알림 — **모두 실제와 동일하게 동작**
- 토스증권 API 주문 전송만 건너뛰고 **가상 체결**로 대체
- 가상 체결가는 요청 시점의 **실제 현재가** 기준으로 계산
- 모든 거래 내역은 `simulation_trades` 테이블에 기록 (실제 `trades`와 완전 분리)
- 봇이 직접 가상 포지션·잔고·수익률을 계산하고 추적
- Discord 알림의 모든 Embed에 `🟡 [시뮬레이션]` 뱃지 표시
- 로그 파일에 `[SIM]` 접두사 포함

```
실전 모드 알림:
  [빈] 매수 체결 — 삼성전자 2주 @ 74,800원

시뮬레이션 모드 알림:
  🟡 [시뮬레이션] [빈] 매수 체결 — 삼성전자 2주 @ 74,800원 (가상)
```

### DRY_RUN 모드 상세

`DRY_RUN=true` 는 개발·디버깅 전용이다.

- AI 호출 없음 (또는 최소화)
- DB 기록 최소화 (영구 보존 데이터 생성 안 함)
- 수익률 추적 안 함
- 개발 완료 후 반드시 `false`로 전환

---

## Safety Gate 통과 조건

실전·시뮬레이션 모드 모두 동일한 조건을 적용한다.
시뮬레이션에서도 Safety Gate가 거부하면 가상 주문도 실행하지 않는다.

```python
# core/safety/gate.py

class SafetyGate:
    async def check(self, order: Order, mode: RunMode) -> GateResult:

        # 0. 수량·금액은 반드시 양수 (0 이하는 5번 조건의 상한 비교를 무력화한다)
        if order.quantity <= 0 or order.amount_krw <= 0:
            return GateResult.reject("주문 수량·금액은 0보다 커야 합니다")

        # 1. 긴급 정지 해제 상태
        if settings.EMERGENCY_STOP:
            return GateResult.reject("EMERGENCY_STOP 활성화")

        # 2. 시장별 정지 플래그
        if mode.market == "KR" and settings.KR_STOP:
            return GateResult.reject("KR_STOP 활성화")
        if mode.market == "US" and settings.US_STOP:
            return GateResult.reject("US_STOP 활성화")

        # 3. 일일 손실 한도 미초과
        #    시뮬레이션: simulation_daily_pnl 기준
        #    실전:       trades 테이블 기준
        daily_loss = await db.get_daily_loss(mode)
        if daily_loss >= settings.MAX_DAILY_LOSS_KRW:
            return GateResult.reject(f"일일 손실 한도 초과: {daily_loss:,} KRW")

        # 4. 단일 종목 비중 상한
        #    시뮬레이션: 가상 포지션 기준
        position_ratio = await portfolio.get_position_ratio(order.symbol, mode)
        if position_ratio > settings.MAX_POSITION_RATIO:
            return GateResult.reject(f"종목 비중 상한 초과: {position_ratio:.1%}")

        # 5. 1회 주문 금액 상한
        if order.amount_krw > settings.MAX_SINGLE_ORDER_KRW:
            return GateResult.reject(f"주문 금액 초과: {order.amount_krw:,} KRW")

        # 6. 현금 버퍼 최소 유지
        #    시뮬레이션: 가상 잔고 기준
        buffer = await portfolio.get_cash_buffer(mode)
        if buffer < settings.INITIAL_SEED_KRW * 0.05:
            return GateResult.reject("현금 버퍼 부족")

        # 7. KR 종목: VI 발동·투자경고·정리매매 없음
        if order.market == "KR":
            warnings = await toss.get_stock_warnings(order.symbol)
            if warnings.has_restriction:
                return GateResult.reject(f"거래 제한 종목: {warnings.reason}")

        # 8. 장 운영 중 확인
        if not await market_calendar.is_open(order.market):
            return GateResult.reject("장 마감 시간")

        # 9. 미국장 금액 주문은 정규장만
        if order.market == "US" and order.type == "AMOUNT":
            if not await market_calendar.is_regular_session("US"):
                return GateResult.reject("금액 주문은 정규장만 허용")

        # 10. 주문 ID 중복 없음
        if await db.order_id_exists(order.client_order_id):
            return GateResult.reject("중복 주문 ID")

        # 11. 고위험 이벤트 당일: 주문 한도 50% 자동 축소
        if await calendar.has_high_risk_event_today():
            limit = settings.MAX_SINGLE_ORDER_KRW * 0.5
            if order.amount_krw > limit:
                return GateResult.reject(f"고위험 이벤트 당일 한도 초과: {limit:,} KRW")

        return GateResult.approve()
```

---

## 거부 처리 흐름

```
Safety Gate 거부
    │
    ├── 거부 사유 로그 기록
    │     실전:        logs/errors/YYYY-MM-DD.log
    │     시뮬레이션:  logs/errors/YYYY-MM-DD.log  [SIM] 접두사
    │
    ├── PostgreSQL safety_rejections 테이블 기록
    │     mode 컬럼: "LIVE" | "SIMULATION" | "DRY_RUN"
    │
    ├── Discord #stock-error Embed 전송
    │     실전:        "[빈] ⚠️ 주문 거부"
    │     시뮬레이션:  "🟡 [시뮬레이션] [빈] ⚠️ 주문 거부"
    │
    └── 호출 코드에 거부 사유 반환 (동일 주문 재시도 금지)
```

---

## 긴급 정지 (Emergency Stop)

```
/stop 명령 수신
    │
    ├── EMERGENCY_STOP = true (DB + Redis 즉시 반영)
    ├── 실전: 모든 미체결 주문 취소 시도
    ├── 시뮬레이션: 가상 미체결 주문 취소 처리
    ├── Discord #stock-system 에 긴급 정지 Embed 발송
    └── 재개는 /resume 명령 + 개발자 확인 필요

/stop kr | /stop us  →  해당 시장만 정지
```

---

## 환경변수

```dotenv
# 운영 모드
DRY_RUN=false          # true: 개발용 최소 테스트
SIMULATION=true        # true: 실전 동일 리허설 (주문만 가상)

# Safety Gate
MAX_DAILY_LOSS_KRW=50000     # 일 최대 손실 한도 (시드의 10%)
MAX_POSITION_RATIO=0.50      # 단일 종목 최대 비중
MAX_SINGLE_ORDER_KRW=100000  # 1회 주문 최대 금액
EMERGENCY_STOP=false
KR_STOP=false
US_STOP=false
```

---

## 하드 금지 사항

- Safety Gate를 우회하는 코드는 절대 작성하지 않는다
- 시뮬레이션 모드라도 Safety Gate는 동일하게 적용한다
- `MAX_DAILY_LOSS_KRW` 초과 후 봇 코드가 자의로 한도를 올리지 않는다
- Discord 명령 없이 Safety Gate 설정을 코드로 변경하지 않는다
- `INITIAL_SEED_KRW` 값은 최초 설정 이후 절대 변경하지 않는다
- 미국장 서머타임 시간을 하드코딩하지 않는다 — 항상 market-calendar API 기준
- `.env` 파일을 git에 커밋하지 않는다
- 실전 DB 테이블(`trades`)과 시뮬레이션 테이블(`simulation_trades`)을 절대 혼용하지 않는다
