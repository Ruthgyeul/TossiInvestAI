"""LIVE/SIMULATION 분기 주문 실행 (docs/BIN.md, docs/SAFETY.md)."""

from core.models import Decision, OrderResult, RunMode


async def execute(decision: Decision, mode: RunMode) -> OrderResult:
    """Safety Gate 통과 후 모드에 따라 실제 주문 또는 가상 체결을 수행한다.

    체결·거부 결과는 Redis `pubsub:events`로 발행해 discord-bot이 구독한다
    (docs/INTERNAL_API.md의 `trade_executed`/`safety_rejection` 이벤트).
    """
    raise NotImplementedError
