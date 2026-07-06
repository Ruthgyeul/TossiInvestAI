"""StateSnapshot → Decision JSON 통합 테스트 (docs/BIN.md)."""

import pytest


@pytest.mark.asyncio
async def test_rule_based_filter_skips_claude_call() -> None:
    pytest.skip("TODO: Phase 3 — trading/decision.py 구현 후 작성")


@pytest.mark.asyncio
async def test_claude_failure_falls_back_to_deepseek() -> None:
    pytest.skip("TODO: Phase 3 — trading/decision.py 구현 후 작성")
