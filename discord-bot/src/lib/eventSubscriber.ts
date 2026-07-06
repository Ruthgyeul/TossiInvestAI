// core → discord-bot 트레이딩 이벤트 구독. Redis `pubsub:events` 채널 단방향 푸시 (docs/INTERNAL_API.md).
import { Client, TextChannel } from "discord.js";
import { Redis } from "ioredis";

import { config } from "../config.js";
import { buildEmergencyStopEmbed, buildHealthAlertEmbed, buildSafetyRejectionEmbed } from "../embeds/alert.js";
import { buildReportEmbed, ReportEmbedData } from "../embeds/report.js";
import { buildBuyEmbed, buildSellEmbed, TradeEmbedData } from "../embeds/trade.js";
import type { StatusData } from "../embeds/status.js";
import { updateStatusEmbed } from "./statusChannel.js";

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

async function getTextChannel(client: Client, channelId: string): Promise<TextChannel | null> {
  const channel = await client.channels.fetch(channelId).catch(() => null);
  return channel instanceof TextChannel ? channel : null;
}

async function logRaw(client: Client, event: PubSubEvent): Promise<void> {
  const channel = await getTextChannel(client, config.channels.log);
  if (!channel) return;
  const line = `[${event.mode}] ${event.event_type} ${JSON.stringify(event.payload)}`.slice(0, 1900);
  await channel.send(line).catch((err) => console.error("log_channel_send_failed", err));
}

async function handleTradeExecuted(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as {
    symbol: string;
    action: "BUY" | "SELL";
    quantity: number;
    fillPrice: number;
    commissionKrw: number;
    pnlKrw: number | null;
    reason: string;
    decisionId: string;
    orderId: string;
  };

  const data: TradeEmbedData = {
    symbol: payload.symbol,
    symbolName: payload.symbol,
    market: event.market ?? "KR",
    quantity: payload.quantity,
    fillPrice: payload.fillPrice,
    commissionKrw: payload.commissionKrw,
    reason: payload.reason,
    decisionId: payload.decisionId,
    orderId: payload.orderId,
    mode: event.mode,
    realizedPnlKrw: payload.pnlKrw ?? undefined,
  };

  const channelId = payload.action === "BUY" ? config.channels.buy : config.channels.sell;
  const embed = payload.action === "BUY" ? buildBuyEmbed(data) : buildSellEmbed(data);
  const channel = await getTextChannel(client, channelId);
  await channel?.send({ embeds: [embed] });
}

async function handleSafetyRejection(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as { symbol: string; action: "BUY" | "SELL"; reason: string };
  const embed = buildSafetyRejectionEmbed({
    symbolName: payload.symbol,
    symbol: payload.symbol,
    attempted: `${payload.action} 시도`,
    reason: payload.reason,
    isSimulation: event.mode !== "LIVE",
  });
  const channel = await getTextChannel(client, config.channels.error);
  await channel?.send({ embeds: [embed] });
}

async function handleEmergencyStop(client: Client, event: PubSubEvent): Promise<void> {
  const embed = buildEmergencyStopEmbed(event.market ?? undefined);
  const channel = await getTextChannel(client, config.channels.system);
  await channel?.send({ embeds: [embed] });
}

async function handleHealthAlert(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as { warnings: string[] };
  const embed = buildHealthAlertEmbed(payload.warnings.join("\n"));
  const channel = await getTextChannel(client, config.channels.error);
  await channel?.send({ embeds: [embed] });
}

async function handleReportReady(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as {
    market: "KR" | "US" | "ALL";
    reportType: ReportEmbedData["reportType"];
    contentMd: string;
    chartPaths: string[];
  };
  const data: ReportEmbedData = {
    market: payload.market,
    reportType: payload.reportType,
    contentMd: payload.contentMd,
    chartFilePaths: payload.chartPaths,
  };
  const embed = buildReportEmbed(data);
  const files = (payload.chartPaths ?? []).map((path) => ({ attachment: path }));
  const channel = await getTextChannel(client, config.channels.analyze);
  await channel?.send({ embeds: [embed], files });
}

async function handleStatusUpdate(client: Client, event: PubSubEvent): Promise<void> {
  await updateStatusEmbed(client, event.payload as unknown as StatusData);
}

async function dispatch(client: Client, event: PubSubEvent): Promise<void> {
  switch (event.event_type) {
    case "trade_executed":
      await handleTradeExecuted(client, event);
      break;
    case "safety_rejection":
      await handleSafetyRejection(client, event);
      break;
    case "emergency_stop":
      await handleEmergencyStop(client, event);
      break;
    case "health_alert":
      await handleHealthAlert(client, event);
      break;
    case "report_ready":
      await handleReportReady(client, event);
      break;
    case "status_update":
      await handleStatusUpdate(client, event);
      break;
    case "backtest_complete":
      // 전용 Embed 없음 — 원래는 correlation_id로 /backtest 인터랙션을 edit해야 하지만
      // (docs/INTERNAL_API.md), 인터랙션 추적 저장소가 없어 이번 Phase는 #stock-log 기록만 한다.
      break;
  }

  await logRaw(client, event);
}

export function subscribeToEvents(client: Client): void {
  const subscriber = new Redis(config.redisUrl);
  subscriber.subscribe("pubsub:events").catch((err) => console.error("pubsub_subscribe_failed", err));

  subscriber.on("message", (_channel, message) => {
    let event: PubSubEvent;
    try {
      event = JSON.parse(message) as PubSubEvent;
    } catch (err) {
      console.error("pubsub_message_parse_failed", err);
      return;
    }

    dispatch(client, event).catch((err) => console.error("pubsub_event_dispatch_failed", event.event_type, err));
  });
}
