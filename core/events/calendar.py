"""FOMC·CPI·실적발표·배당락 등 시장 이벤트 캘린더 (docs/BIN.md).

고위험 이벤트 당일에는 Safety Gate가 1회 주문 한도를 자동 50% 축소한다.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.db import store as db
from core.models import Market

_KST = ZoneInfo("Asia/Seoul")


def _kst_date(event_at: datetime) -> date:
    return event_at.astimezone(_KST).date()


async def get_events_today(market: Market) -> list[dict]:
    events = await db.fetch_all("market_events", {"market": market})
    today = datetime.now(_KST).date()
    return [e for e in events if _kst_date(e["event_at"]) == today]


async def has_high_risk_event(on_date: date) -> bool:
    events = await db.fetch_all("market_events", {"is_high_risk": True})
    return any(_kst_date(e["event_at"]) == on_date for e in events)


async def has_high_risk_event_today() -> bool:
    return await has_high_risk_event(datetime.now(_KST).date())
