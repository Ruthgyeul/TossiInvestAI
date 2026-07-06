"""core → discord-bot 단방향 이벤트 발행. Redis `pubsub:events` 채널 하나만 사용한다 (docs/INTERNAL_API.md).

discord-bot의 eventSubscriber.ts가 이 채널을 구독해 event_type별로 Embed를 렌더링한다.
"""

import json
from datetime import datetime, timezone
from typing import Any, Literal

from core.db.redis import get_redis
from core.models import Market, Mode

EventType = Literal[
    "trade_executed",
    "safety_rejection",
    "emergency_stop",
    "health_alert",
    "report_ready",
    "backtest_complete",
    "status_update",
]

_CHANNEL = "pubsub:events"


async def publish_event(
    event_type: EventType,
    *,
    mode: Mode,
    market: Market | None,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> None:
    envelope = {
        "event_type": event_type,
        "mode": mode,
        "market": market,
        "correlation_id": correlation_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    redis = get_redis()
    await redis.publish(_CHANNEL, json.dumps(envelope))
