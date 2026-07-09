// core/api/monitor_snapshot.py가 "시스템 상태" 카드의 discord-bot 가동 시간을 읽어가는
// Redis 키. core 프로세스는 psutil로 자기 프로세스 시작 시각을 직접 잴 수 있지만
// discord-bot은 별도 프로세스라 core가 직접 잴 방법이 없다 — 그래서 준비 완료 시점에
// 여기 한 번만 기록한다 (docs/MONITOR.md "외부 접속 인증"이 아니라 "시스템 상태" 참고).
import { Redis } from "ioredis";

import { config } from "../config.js";

const REDIS_KEY = "service:started_at:discord-bot";

export async function recordServiceStarted(): Promise<void> {
  const redis = new Redis(config.redisUrl);
  try {
    await redis.set(REDIS_KEY, new Date().toISOString());
  } catch (err) {
    console.error("[빈] 서비스 시작 시각 기록 실패", err);
  } finally {
    await redis.quit().catch(() => undefined);
  }
}
