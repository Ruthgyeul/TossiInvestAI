"""SafetyGate 통과·거부 조건 단위 테스트 (docs/SAFETY.md 11개 조건, KR·US 시나리오)."""

import pytest

from core.safety.gate import SafetyGate


@pytest.fixture
def gate() -> SafetyGate:
    return SafetyGate()


@pytest.mark.asyncio
async def test_emergency_stop_rejects_all_orders(gate: SafetyGate) -> None:
    pytest.skip("TODO: Phase 2 — safety/gate.py 구현 후 작성")


@pytest.mark.asyncio
async def test_max_position_ratio_rejects_oversized_order(gate: SafetyGate) -> None:
    pytest.skip("TODO: Phase 2 — safety/gate.py 구현 후 작성")
