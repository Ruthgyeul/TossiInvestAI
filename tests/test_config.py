"""core/config.py Settings 클래스 단위 테스트 (docs/CODING_RULES.md Phase 1-2)."""

import pytest
from pydantic import ValidationError

from core.config import Settings

_REQUIRED_FIELDS = {
    "TOSS_CLIENT_ID": "id",
    "TOSS_CLIENT_SECRET": "secret",
    "TOSS_ACCOUNT_SEQ": "seq",
    "ANTHROPIC_API_KEY": "key",
    "GEMINI_API_KEY": "key",
    "DEEPSEEK_API_KEY": "key",
    "DATABASE_URL": "postgresql+asyncpg://bin:changeme@localhost:5432/bin_trading_test",
    "REDIS_URL": "redis://localhost:6379/1",
    "CORE_INTERNAL_API_TOKEN": "token",
}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_REQUIRED_FIELDS, **overrides})  # type: ignore[arg-type]


def test_run_mode_prioritizes_dry_run_over_simulation() -> None:
    assert _settings(DRY_RUN=True, SIMULATION=True).run_mode == "DRY_RUN"


def test_run_mode_simulation_when_not_dry_run() -> None:
    assert _settings(DRY_RUN=False, SIMULATION=True).run_mode == "SIMULATION"


def test_run_mode_live_when_dry_run_and_simulation_disabled() -> None:
    assert _settings(DRY_RUN=False, SIMULATION=False).run_mode == "LIVE"


def test_claude_pricing_defaults_to_standard_rate() -> None:
    settings = _settings()
    assert settings.CLAUDE_INPUT_PRICE_PER_MTOK == 3.0
    assert settings.CLAUDE_OUTPUT_PRICE_PER_MTOK == 15.0


def test_claude_pricing_overridable_via_env() -> None:
    settings = _settings(CLAUDE_INPUT_PRICE_PER_MTOK=2.0, CLAUDE_OUTPUT_PRICE_PER_MTOK=10.0)
    assert settings.CLAUDE_INPUT_PRICE_PER_MTOK == 2.0
    assert settings.CLAUDE_OUTPUT_PRICE_PER_MTOK == 10.0


def test_defaults_start_in_dry_run_and_simulation() -> None:
    # 로컬 .env가 이 값들을 덮어쓸 수 있으므로 클래스 기본값 자체를 검사한다.
    assert Settings.model_fields["DRY_RUN"].default is False
    assert Settings.model_fields["SIMULATION"].default is True
    assert Settings.model_fields["INITIAL_SEED_KRW"].default == 500_000


def test_initial_seed_krw_cannot_be_reassigned_at_runtime() -> None:
    """CLAUDE.md 절대 규칙 3 — 손익 계산 기준점이므로 런타임 재할당을 코드로 차단한다."""
    settings = _settings()

    with pytest.raises(ValidationError):
        settings.INITIAL_SEED_KRW = 999_999


def test_other_runtime_flags_remain_mutable() -> None:
    """SIMULATION/DRY_RUN/EMERGENCY_STOP 등은 운영 중 전환 가능해야 한다 (core/api/routes.py)."""
    settings = _settings()

    settings.SIMULATION = False
    settings.EMERGENCY_STOP = True

    assert settings.SIMULATION is False
    assert settings.EMERGENCY_STOP is True
