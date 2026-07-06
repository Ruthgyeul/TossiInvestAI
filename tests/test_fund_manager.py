"""FundManager 자금 배분·API 비용 기록 단위 테스트 (docs/FUND_MANAGER.md)."""

import pytest

from core.fund.manager import FundManager


@pytest.fixture
def fund_manager() -> FundManager:
    return FundManager()


def test_can_allocate_rejects_over_position_ratio(fund_manager: FundManager) -> None:
    pytest.skip("TODO: Phase 2 — fund/manager.py 구현 후 작성")


def test_record_api_usage_applies_cache_pricing(fund_manager: FundManager) -> None:
    pytest.skip("TODO: Phase 2 — fund/manager.py 구현 후 작성")
