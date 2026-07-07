# DISCORD.md — Discord 봇

---

## 기술 스택

- **Runtime**: Node.js (LTS)
- **언어**: TypeScript
- **라이브러리**: Discord.js v14+
- **운영**: 24/7 (systemd `bin-discord.service`)

---

## 설정 파일 관리

Discord 관련 ID와 토큰은 `.env` 또는 별도 `discord-bot/config.ts`에서만 로드한다.
소스코드에 하드코딩 절대 금지.

```dotenv
# .env
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_STATUS_CHANNEL_ID=
DISCORD_ANALYZE_CHANNEL_ID=
DISCORD_BUY_CHANNEL_ID=
DISCORD_SELL_CHANNEL_ID=
DISCORD_SYSTEM_CHANNEL_ID=
DISCORD_ERROR_CHANNEL_ID=
DISCORD_NEWS_CHANNEL_ID=
DISCORD_LOG_CHANNEL_ID=

# core 내부 API·Redis (docs/INTERNAL_API.md)
CORE_INTERNAL_API_URL=http://127.0.0.1:8000
CORE_INTERNAL_API_TOKEN=
REDIS_URL=redis://127.0.0.1:6379/0
```

---

## 채널 구성

| 채널명 | 용도 | 업데이트 방식 |
|--------|------|---------------|
| `#status` | 실시간 포트폴리오 손익, 보유 주식 현황 | Embed 메시지 **지속 수정(edit)** — 고정 메시지 1개 유지 |
| `#stock-analyze` | 시장 리포트, 분석 결과 | 리포트 발송마다 새 Embed |
| `#stock-buy` | 매수 체결 알림 | 체결마다 새 Embed |
| `#stock-sell` | 매도 체결 알림 | 체결마다 새 Embed |
| `#stock-system` | 에이전트 상태, Reflection 리포트, 재시작 알림 | 이벤트마다 새 Embed |
| `#stock-error` | Safety Gate 거부, 에러, 장애 알림 | 이벤트마다 새 Embed |
| `#stock-news` | 종목 관련 뉴스 요약 | 뉴스 수집마다 |
| `#stock-log` | 전체 이벤트 텍스트 로그 (디버그용) | append |

> **채널 삭제는 불가능하다.** 봇은 필요 시 카테고리 하위 채널 생성만 가능.
> 모든 메시지는 Embed 형식으로 전송한다.

---

## #status 채널 운영 방식

봇 최초 시작 시 `#status` 채널에 Embed 메시지를 1개 전송하고
이후 **동일 메시지를 주기적으로 edit**하여 최신 상태를 유지한다.

```
[빈] 포트폴리오 현황
──────────────────────────────
💰 총 자산      512,300 KRW
📈 오늘 손익   +3,200 KRW (+0.63%)
📊 누적 손익  +12,300 KRW (+2.46%)
──────────────────────────────
🇰🇷 한국장
  삼성전자(005930)  2주  74,800원  +1.2%
  SK하이닉스(000660)  1주  186,500원  -0.3%
🇺🇸 미국장
  NVDA  0.5주  $128.40  +2.1%
──────────────────────────────
💵 현금 버퍼    76,800 KRW
🔄 마지막 업데이트  2026-07-05 10:45 KST
```

---

## Slash 명령어

| 명령어 | 설명 |
|--------|------|
| `/status` | 전체 포트폴리오 현황 (KR·US 통합) |
| `/status kr` / `/status us` | 시장별 현황만 조회 |
| `/buy {symbol} {qty} [price]` | 수동 매수 (price 생략 → 시장가) |
| `/sell {symbol} {qty} [price]` | 수동 매도 |
| `/cancel {orderId}` | 미체결 주문 취소 |
| `/stop` | 전체 자동매매 즉시 중단 |
| `/stop kr` / `/stop us` | 특정 시장만 중단 |
| `/resume` | 자동매매 재개 |
| `/simulate on\|off` | 시뮬레이션 모드 전환 (실전 동일 리허설, 주문만 가상) |
| `/dryrun on\|off` | DRY_RUN 모드 전환 (개발·디버깅 전용) |
| `/simstatus` | 시뮬레이션 누적 성과 — 가상 수익률·거래 횟수·승률·MDD |
| `/report` | 즉시 통합 리포트 생성·발송 |
| `/report kr` / `/report us` | 시장별 즉시 리포트 |
| `/holdings` | 보유 종목 목록 |
| `/orders` | 미체결 주문 목록 |
| `/fund` | 자금 배분 현황 (슬롯별 잔고, 버퍼, 누적 수익) |
| `/apicost` | 이번 달 Claude API 사용 비용 추정 |
| `/watchlist` | 관심 종목 목록 |
| `/watchlist add {symbol}` | 관심 종목 수동 추가 |
| `/watchlist remove {symbol}` | 관심 종목 제거 |
| `/backtest {strategy} {period}` | 백테스트 실행 (1Y/3Y/5Y) |
| `/health` | 라즈베리파이 상태 (CPU·메모리·온도·디스크) |
| `/version` | 현재 전략·프롬프트 버전 |
| `/version candidates` | 승인 대기 중인 자기개선 후보 목록 (docs/SELF_IMPROVEMENT.md) |
| `/version approve {id}` | 후보를 승인해 배포 상태로 전환 |
| `/version reject {id}` | 후보 거부 |
| `/version rollback {strategyVersion}` | 과거 배포 이력이 있는 버전으로 롤백 |

---

## 명령어 권한

자금·주문·운영 모드·배포 상태를 바꾸는 명령(`/buy`, `/sell`, `/cancel`, `/stop`,
`/resume`, `/simulate`, `/dryrun`, `/watchlist add|remove`, `/version approve|reject|rollback`)은
`SlashCommandBuilder.setDefaultMemberPermissions(PermissionFlagsBits.Administrator)`로
기본값을 관리자 전용으로 제한한다 — 길드에 개발자 외 멤버가 있어도 기본 상태에서는
실행할 수 없다. 조회 전용 명령(`/status`, `/holdings`, `/orders`, `/fund`, `/apicost`,
`/health`, `/simstatus`, `/report`, `/backtest`, `/version`(인자 없음))은 제한하지 않는다.
필요하면 길드 설정(서버 설정 → 통합 → 앱)에서 특정 역할에 개별적으로 권한을 더 열어줄 수 있다.

---

## Embed 메시지 형식

모든 Embed는 아래 공통 구조를 따른다.

```typescript
{
  author: { name: "빈(Bin)", iconURL: BOT_AVATAR_URL },
  color: /* 매수: 0x00b894, 매도: 0xe17055, 정보: 0x0984e3, 경고: 0xfdcb6e, 에러: 0xd63031 */,
  title: "...",
  description: "...",
  fields: [...],
  footer: { text: `빈 | ${timestamp}` },
  timestamp: new Date()
}
```

### 매수 알림 (#stock-buy)

```
[빈] 매수 체결
──────────────────────────────
🟢 삼성전자 (005930) · 한국장
  수량    2주
  체결가  74,800원
  총금액  149,600원
  수수료  224원
  판단 이유  RSI 반등 + 거래량 확인
  Decision ID  a3f2b1c4-...
  Order ID     TOSS-20260705-001
```

### 매수 알림 — 시뮬레이션 (#stock-buy)

```
🟡 [시뮬레이션] [빈] 매수 체결 (가상)
──────────────────────────────
삼성전자 (005930) · 한국장
  수량          2주
  가상 체결가   74,800원  (요청 시점 실제 현재가)
  총금액        149,600원
  수수료        224원 (실제 요율 적용)
  가상 잔고     -149,824원 차감
  판단 이유     RSI 반등 + 거래량 확인
  Decision ID   a3f2b1c4-...
  Order ID      SIM-20260706-KR-001
```

### 매도 알림 (#stock-sell)

```
[빈] 매도 체결
──────────────────────────────
🔴 삼성전자 (005930) · 한국장
  수량      2주
  체결가    76,200원
  평균단가  74,800원
  실현손익  +2,800원 (+1.87%)
  수수료    228원
  판단 이유  목표가 도달
  Decision ID  b1c2d3e4-...
  Order ID     TOSS-20260705-002
```

### Safety Gate 거부 알림 (#stock-error)

```
[빈] ⚠️ 주문 거부
──────────────────────────────
종목    삼성전자 (005930)
시도    매수 2주
거부 사유  일일 손실 한도 초과
          (오늘 손실: 52,000 KRW / 한도: 50,000 KRW)
```

---

## 봇 아키텍처 (TypeScript)

```typescript
// discord-bot/src/config.ts
export const config = {
  token: process.env.DISCORD_BOT_TOKEN!,
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
  }
}
```

Discord 봇은 Python 트레이딩 코어와 **Redis pub/sub** 또는 **HTTP 내부 API**로 통신한다.
트레이딩 코어가 이벤트를 발행하면 Discord 봇이 구독해 Embed를 전송하는 단방향 흐름.
개발자 명령은 Discord 봇이 수신해 Python 코어에 HTTP POST로 전달한다.
