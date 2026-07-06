"""장 마감 후 자기평가. KR 15:40 / US 06:10 (KST) 1회 실행 (docs/BIN.md)."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import structlog

from core.config import settings
from core.db import store as db
from core.events.publisher import publish_event
from core.models import Market, Mode

log = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_REFLECTIONS_DIR = Path("logs/reports")

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

_REFLECTION_SYSTEM_PROMPT = (
    "너는 빈(Bin)의 자기평가 보조 AI다. 아래 오늘자 매매 내역과 Safety Gate 거부 이력을 검토해 "
    "한국어 마크다운 목록으로 다음 네 항목을 각각 한두 문장으로 평가하라.\n"
    "1. 오늘 매매가 적절했는가\n"
    "2. 놓친 매수/매도 기회는 무엇인가\n"
    "3. Safety Gate 거부 중 옳았던 것은 무엇인가\n"
    "4. 내일 개선할 점은 무엇인가\n\n"
    "마지막 줄은 반드시 `PROPOSED_CHANGE:`로 시작해야 한다(자기개선 파이프라인이 이 줄만 "
    "파싱한다). 프롬프트 문구나 전략 파라미터에 구체적인 개선안이 있으면 "
    "`PROPOSED_CHANGE: <한 문장 요약>`으로, 없으면 `PROPOSED_CHANGE: 없음`으로 적어라."
)


def _extract_proposed_change(content_md: str) -> str | None:
    """docs/SELF_IMPROVEMENT.md "개선안 초안 생성" — Claude 응답의 `PROPOSED_CHANGE:` 줄만
    파싱한다(별도 Claude 호출 없이 하루 1회 Reflection 결과를 재사용, 하드 금지 사항 마지막 항목)."""
    for line in reversed(content_md.splitlines()):
        stripped = line.strip()
        if stripped.upper().startswith("PROPOSED_CHANGE:"):
            value = stripped.split(":", 1)[1].strip()
            return None if value in ("", "없음") else value
    return None


def _summarize_trades(trades: list[dict]) -> str:
    if not trades:
        return "체결 없음"
    lines = []
    for t in trades:
        pnl = t.get("pnl_krw")
        pnl_str = f", 손익 {pnl:+,} KRW" if pnl is not None else ""
        lines.append(f"- {t['action']} {t['symbol']} {t['quantity']}주 @ {t['fill_price']:,}{pnl_str}")
    return "\n".join(lines)


def _summarize_rejections(rejections: list[dict]) -> str:
    if not rejections:
        return "거부 없음"
    return "\n".join(f"- {r['symbol']}: {r['reason']}" for r in rejections)


async def _call_claude_reflection(market: Market, trades: list[dict], rejections: list[dict]) -> str:
    """자기평가는 하루 1회뿐이라 Prompt Caching을 적용하지 않는다 (docs/BIN.md)."""
    user_message = (
        f"[{market} 시장 오늘 체결 내역]\n{_summarize_trades(trades)}\n\n"
        f"[{market} 시장 오늘 Safety Gate 거부 내역]\n{_summarize_rejections(rejections)}"
    )
    response = await _client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=settings.CLAUDE_MAX_TOKENS,
        system=_REFLECTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    from core.fund.manager import fund_manager

    await fund_manager.record_api_usage(
        model=settings.CLAUDE_MODEL,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    block = response.content[0]
    if not isinstance(block, anthropic.types.TextBlock):
        raise ValueError(f"Claude 응답이 텍스트 블록이 아님: {type(block).__name__}")
    return block.text


def _reflection_filename(market: Market, now: datetime) -> Path:
    _REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _REFLECTIONS_DIR / f"reflection_{now:%Y-%m-%d}_{market.lower()}.md"


async def run_reflection(market: Market) -> None:
    """오늘 매매 적절성·놓친 기회·Safety Gate 거부 타당성·개선점을 Claude에 질의하고
    reflections 테이블 + logs/reports/reflection_YYYY-MM-DD.md 에 저장한다."""
    mode: Mode = settings.run_mode  # type: ignore[assignment]
    trade_mode: Mode = "LIVE" if mode == "LIVE" else "SIMULATION"

    trades = await db.get_today_trades(trade_mode, market)
    rejections = await db.get_today_rejections(market)

    content_md = await _call_claude_reflection(market, trades, rejections)
    proposed_change = _extract_proposed_change(content_md)

    now = datetime.now(_KST)
    full_content = f"# [빈] {market} 자기평가 — {now:%Y-%m-%d} (장 마감 후)\n\n{content_md}"

    await db.insert(
        "reflections",
        {
            "market": market,
            "mode": mode,
            "content_md": full_content,
            "proposed_change": proposed_change,
        },
    )
    _reflection_filename(market, now).write_text(full_content, encoding="utf-8")

    log.info("reflection_completed", market=market, mode=mode)
    await publish_event(
        "reflection_ready",
        mode=mode,
        market=market,
        payload={"market": market, "contentMd": full_content[:3800]},
    )

    if proposed_change:
        from core.trading.self_improvement import propose_candidate

        try:
            await propose_candidate(market, proposed_change)
        except Exception as e:  # noqa: BLE001 — 후보 제안 실패가 Reflection 자체를 실패시키면 안 된다
            log.warning("self_improvement_propose_failed", market=market, error=str(e))
