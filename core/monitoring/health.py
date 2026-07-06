"""라즈베리파이 헬스 모니터링. 매 5분 수집, 임계값 초과 시 #stock-error 알림 (docs/LOGGING.md)."""

from dataclasses import dataclass

CPU_THRESHOLD_PCT = 85.0
MEMORY_THRESHOLD_PCT = 80.0
DISK_THRESHOLD_PCT = 90.0
TEMP_THRESHOLD_C = 75.0
TOSS_API_TIMEOUT_S = 30.0


@dataclass
class HealthSnapshot:
    cpu_pct: float
    memory_pct: float
    disk_pct: float
    temp_c: float
    toss_api_reachable: bool


async def collect_health_snapshot() -> HealthSnapshot:
    raise NotImplementedError


def check_thresholds(snapshot: HealthSnapshot) -> list[str]:
    """임계값을 초과한 항목의 경고 메시지 목록을 반환한다."""
    raise NotImplementedError
