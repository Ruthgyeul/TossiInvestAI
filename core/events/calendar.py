"""FOMC·CPI·실적발표·배당락 등 시장 이벤트 캘린더 (docs/BIN.md).

고위험 이벤트 당일에는 Safety Gate가 1회 주문 한도를 자동 50% 축소한다.
"""

from datetime import date

from core.models import Market


async def get_events_today(market: Market) -> list[dict]:
    raise NotImplementedError


async def has_high_risk_event_today() -> bool:
    raise NotImplementedError


async def has_high_risk_event(on_date: date) -> bool:
    raise NotImplementedError
