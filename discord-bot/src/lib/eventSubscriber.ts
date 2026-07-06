// core → discord-bot 트레이딩 이벤트 구독. Redis `pubsub:events` 채널 단방향 푸시 (docs/INTERNAL_API.md).
import type { Client } from "discord.js";

export interface PubSubEvent {
  event_type:
    | "trade_executed"
    | "safety_rejection"
    | "emergency_stop"
    | "health_alert"
    | "report_ready"
    | "backtest_complete"
    | "status_update";
  mode: "LIVE" | "SIMULATION" | "DRY_RUN";
  market: "KR" | "US" | null;
  correlation_id: string | null;
  published_at: string;
  payload: Record<string, unknown>;
}

export function subscribeToEvents(client: Client): void {
  throw new Error("Not implemented");
}
