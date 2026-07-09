"""라즈베리파이 헬스 모니터링. 매 5분 수집, 임계값 초과 시 #stock-error 알림 (docs/LOGGING.md)."""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import psutil

from core.config import settings
from core.db.redis import get_redis
from core.events.publisher import publish_event
from core.toss import client as toss_client

CPU_THRESHOLD_PCT = 85.0
MEMORY_THRESHOLD_PCT = 80.0
DISK_THRESHOLD_PCT = 90.0
TEMP_THRESHOLD_C = 75.0
TOSS_API_TIMEOUT_S = 30.0

HEALTH_REDIS_KEY = "health:latest"


@dataclass
class HealthSnapshot:
    cpu_pct: float
    memory_pct: float
    disk_pct: float
    temp_c: float
    toss_api_reachable: bool
    # docs/MONITOR.md "시스템 상태" 카드의 "HB N초 전"이 실제 경과 시간을 보여주려면
    # 수집 시각이 스냅샷에 실려 있어야 한다 (이전에는 신선도를 알 방법이 없었다).
    collected_at: str = ""


def _read_sync_metrics() -> tuple[float, float, float]:
    """psutil 호출은 블로킹이므로 asyncio.to_thread로 격리해 이벤트 루프를 막지 않는다."""
    return (
        psutil.cpu_percent(interval=1),
        psutil.virtual_memory().percent,
        psutil.disk_usage("/").percent,
    )


def _read_cpu_temp_c() -> float:
    try:
        temps = psutil.sensors_temperatures()
    except AttributeError:
        return 0.0
    for readings in temps.values():
        if readings:
            return float(readings[0].current)
    return 0.0


async def _check_toss_reachable() -> bool:
    try:
        async with asyncio.timeout(TOSS_API_TIMEOUT_S):
            await toss_client.request("GET", "/api/v1/exchange-rate", "MARKET_INFO")
        return True
    except Exception:  # noqa: BLE001 — 헬스체크는 어떤 이유로든 실패하면 unreachable로 취급한다
        return False


async def collect_health_snapshot() -> HealthSnapshot:
    cpu_pct, memory_pct, disk_pct = await asyncio.to_thread(_read_sync_metrics)
    snapshot = HealthSnapshot(
        cpu_pct=cpu_pct,
        memory_pct=memory_pct,
        disk_pct=disk_pct,
        temp_c=_read_cpu_temp_c(),
        toss_api_reachable=await _check_toss_reachable(),
        collected_at=datetime.now(UTC).isoformat(),
    )

    redis = get_redis()
    await redis.set(HEALTH_REDIS_KEY, json.dumps(asdict(snapshot)))
    return snapshot


def check_thresholds(snapshot: HealthSnapshot) -> list[str]:
    """임계값을 초과한 항목의 경고 메시지 목록을 반환한다."""
    warnings: list[str] = []
    if snapshot.cpu_pct > CPU_THRESHOLD_PCT:
        warnings.append(f"CPU 사용률 {snapshot.cpu_pct:.1f}% > {CPU_THRESHOLD_PCT:.0f}%")
    if snapshot.memory_pct > MEMORY_THRESHOLD_PCT:
        warnings.append(f"메모리 사용률 {snapshot.memory_pct:.1f}% > {MEMORY_THRESHOLD_PCT:.0f}%")
    if snapshot.disk_pct > DISK_THRESHOLD_PCT:
        warnings.append(f"디스크 사용량 {snapshot.disk_pct:.1f}% > {DISK_THRESHOLD_PCT:.0f}%")
    if snapshot.temp_c > TEMP_THRESHOLD_C:
        warnings.append(f"CPU 온도 {snapshot.temp_c:.1f}°C > {TEMP_THRESHOLD_C:.0f}°C")
    if not snapshot.toss_api_reachable:
        warnings.append(f"토스 API 응답 없음 (> {TOSS_API_TIMEOUT_S:.0f}s)")
    return warnings


async def run_health_check() -> HealthSnapshot:
    """스케줄러가 5분마다 호출하는 진입점 — 수집 → 임계값 검사 → 초과 시 알림 발행."""
    snapshot = await collect_health_snapshot()
    warnings = check_thresholds(snapshot)
    if warnings:
        await publish_event(
            "health_alert",
            mode=settings.run_mode,
            market=None,
            payload={"warnings": warnings, "snapshot": asdict(snapshot)},
        )
    return snapshot
