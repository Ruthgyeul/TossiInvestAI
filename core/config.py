"""모든 설정의 단일 진입점. core 어디서든 `from core.config import settings`로 불러온다."""

from datetime import date
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 토스증권
    TOSS_CLIENT_ID: str
    TOSS_CLIENT_SECRET: str
    TOSS_ACCOUNT_SEQ: str
    TOSS_BASE_URL: str = "https://openapi.tossinvest.com"

    # AI Gateway
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 512
    GEMINI_API_KEY: str
    DEEPSEEK_API_KEY: str

    # DB
    DATABASE_URL: str
    REDIS_URL: str

    # 자금 — INITIAL_SEED_KRW는 손익 계산 기준점이므로 절대 변경 금지 (docs/SAFETY.md)
    INITIAL_SEED_KRW: int = 500_000
    CASH_BUFFER_RATIO: float = 0.15

    # Safety Gate
    MAX_DAILY_LOSS_KRW: int = 50_000
    MAX_POSITION_RATIO: float = 0.50
    MAX_SINGLE_ORDER_KRW: int = 100_000
    EMERGENCY_STOP: bool = False
    KR_STOP: bool = False
    US_STOP: bool = False

    # 운영 모드
    DRY_RUN: bool = False        # true: 개발용 최소 테스트
    SIMULATION: bool = True      # true: 실전 동일 리허설 (주문만 가상)
    LOG_LEVEL: str = "INFO"

    @property
    def run_mode(self) -> Literal["DRY_RUN", "SIMULATION", "LIVE"]:
        if self.DRY_RUN:
            return "DRY_RUN"
        if self.SIMULATION:
            return "SIMULATION"
        return "LIVE"

    # 가격 자동 전환 (introductory → standard 2026-08-31 이후)
    @property
    def claude_input_price_per_mtok(self) -> float:
        return 2.0 if date.today().isoformat() <= "2026-08-31" else 3.0

    @property
    def claude_output_price_per_mtok(self) -> float:
        return 10.0 if date.today().isoformat() <= "2026-08-31" else 15.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
