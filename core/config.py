"""모든 설정의 단일 진입점. core 어디서든 `from core.config import settings`로 불러온다."""

from typing import Literal

from pydantic import Field
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
    GEMINI_MODEL: str = "gemini-2.0-flash"
    DEEPSEEK_API_KEY: str
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_MAX_TOKENS: int = 512

    # Claude 단가 (KRW 환산은 core/fund/manager.py) — 요금제가 바뀌면 코드 수정 없이
    # .env만 바꿔 반영한다. 기본값은 standard 요금제 기준.
    CLAUDE_INPUT_PRICE_PER_MTOK: float = 3.0
    CLAUDE_OUTPUT_PRICE_PER_MTOK: float = 15.0

    # DB
    DATABASE_URL: str
    REDIS_URL: str

    # 내부 API — discord-bot이 보내는 요청을 검증하는 공유 토큰 (docs/INTERNAL_API.md)
    CORE_INTERNAL_API_TOKEN: str

    # 자금 — INITIAL_SEED_KRW는 손익 계산 기준점이므로 절대 변경 금지 (docs/SAFETY.md).
    # frozen=True로 최초 로드 이후 런타임 재할당을 코드 레벨에서 차단한다
    # (CLAUDE.md 절대 규칙 3 — 값을 바꾸려면 .env를 고쳐 프로세스를 재기동해야 한다).
    INITIAL_SEED_KRW: int = Field(default=500_000, frozen=True)
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
