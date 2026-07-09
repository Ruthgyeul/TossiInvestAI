// core → discord-bot 트레이딩 이벤트 구독. Redis `pubsub:events` 채널 단방향 푸시 (docs/INTERNAL_API.md).
import { Client } from "discord.js";
import { Redis } from "ioredis";

import { config } from "../config.js";
import {
  buildEmergencyStopEmbed,
  buildHealthAlertEmbed,
  buildReflectionEmbed,
  buildSafetyRejectionEmbed,
} from "../embeds/alert.js";
import { buildInfoEmbed } from "../embeds/info.js";
import { buildMonitorAuthCodeEmbed } from "../embeds/monitorAuth.js";
import { buildNewsEmbed } from "../embeds/news.js";
import { buildReportEmbed, ReportEmbedData } from "../embeds/report.js";
import { buildBuyEmbed, buildSellEmbed, TradeEmbedData } from "../embeds/trade.js";
import type { StatusData } from "../embeds/status.js";
import { getChannel } from "./channels.js";
import { resolveInteraction } from "./interactionTracker.js";
import { updateStatusEmbed } from "./statusChannel.js";

export interface PubSubEvent {
  event_type:
    | "trade_executed"
    | "safety_rejection"
    | "emergency_stop"
    | "health_alert"
    | "report_ready"
    | "backtest_complete"
    | "status_update"
    | "reflection_ready"
    | "news_summary"
    | "version_candidate_ready"
    | "monitor_auth_code_issued";
  // monitor publishes "SYSTEM" for monitor_auth_code_issued (docs/MONITOR.md) — the type
  // stays 3-valued because `JSON.parse(...) as PubSubEvent` in subscribeToEvents() is an
  // unchecked assertion, and no other event_type's handler ever sees that runtime value.
  mode: "LIVE" | "SIMULATION" | "DRY_RUN";
  market: "KR" | "US" | null;
  correlation_id: string | null;
  published_at: string;
  payload: Record<string, unknown>;
}

async function logRaw(client: Client, event: PubSubEvent): Promise<void> {
  const channel = await getChannel(client, "log");
  if (!channel) return;
  // monitor_auth_code_issued의 코드는 DM 전용이다 — 길드에서 보이는 로그 채널에는 절대 남기지 않는다.
  const payload =
    event.event_type === "monitor_auth_code_issued" ? { ...event.payload, code: "[REDACTED]" } : event.payload;
  const line = `[${event.mode}] ${event.event_type} ${JSON.stringify(payload)}`.slice(0, 4000);
  const embed = buildInfoEmbed("[빈] 이벤트 로그", `\`\`\`\n${line}\n\`\`\``);
  await channel.send({ embeds: [embed] }).catch((err) => console.error("log_channel_send_failed", err));
}

async function handleTradeExecuted(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as {
    symbol: string;
    action: "BUY" | "SELL";
    quantity: number;
    fillPrice: number;
    totalAmountKrw?: number;
    commissionKrw: number;
    pnlKrw: number | null;
    avgPrice?: number | null;
    balanceChangeKrw?: number | null;
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
    totalAmountKrw: payload.totalAmountKrw ?? payload.fillPrice * payload.quantity,
    commissionKrw: payload.commissionKrw,
    reason: payload.reason,
    decisionId: payload.decisionId,
    orderId: payload.orderId,
    mode: event.mode,
    realizedPnlKrw: payload.pnlKrw ?? undefined,
    avgPrice: payload.avgPrice ?? undefined,
    balanceChangeKrw: payload.balanceChangeKrw ?? undefined,
  };

  const embed = payload.action === "BUY" ? buildBuyEmbed(data) : buildSellEmbed(data);
  const channel = await getChannel(client, payload.action === "BUY" ? "buy" : "sell");
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
  const channel = await getChannel(client, "error");
  await channel?.send({ embeds: [embed] });
}

async function handleEmergencyStop(client: Client, event: PubSubEvent): Promise<void> {
  const embed = buildEmergencyStopEmbed(event.market ?? undefined);
  const channel = await getChannel(client, "system");
  await channel?.send({ embeds: [embed] });
}

async function handleHealthAlert(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as { warnings: string[] };
  const embed = buildHealthAlertEmbed(payload.warnings.join("\n"));
  const channel = await getChannel(client, "error");
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

  // /report가 발급한 jobId(correlation_id)와 일치하는 인터랙션이 있으면 그 자리에서 마무리하고,
  // 없으면(봇 재시작 등) #stock-analyze에 게시한다 (docs/INTERNAL_API.md "동기 vs 지연 응답").
  const interaction = resolveInteraction(event.correlation_id);
  if (interaction) {
    await interaction.editReply({ embeds: [embed], files });
    return;
  }
  const channel = await getChannel(client, "analyze");
  await channel?.send({ embeds: [embed], files });
}

async function handleBacktestComplete(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as {
    error?: string;
    winRate?: number;
    avgReturn?: number;
    mdd?: number;
    sharpeRatio?: number;
    profitFactor?: number;
  };

  const embed = payload.error
    ? buildInfoEmbed("[빈] ⏳ 백테스트 결과", payload.error, 0xfdcb6e)
    : buildInfoEmbed(
        "[빈] 📈 백테스트 결과",
        [
          `승률            ${((payload.winRate ?? 0) * 100).toFixed(1)}%`,
          `평균 수익률     ${((payload.avgReturn ?? 0) * 100).toFixed(2)}%`,
          `MDD             ${((payload.mdd ?? 0) * 100).toFixed(2)}%`,
          `샤프 지수       ${(payload.sharpeRatio ?? 0).toFixed(2)}`,
          `수익 팩터       ${(payload.profitFactor ?? 0).toFixed(2)}`,
        ].join("\n"),
      );

  // /backtest가 발급한 jobId(correlation_id)와 일치하는 인터랙션을 edit한다 — 전용 채널이
  // 없으므로(docs/INTERNAL_API.md) 매칭되는 인터랙션이 없으면 #stock-log 기록만 남긴다.
  const interaction = resolveInteraction(event.correlation_id);
  if (interaction) {
    await interaction.editReply({ embeds: [embed] });
  }
}

async function handleStatusUpdate(client: Client, event: PubSubEvent): Promise<void> {
  await updateStatusEmbed(client, event.payload as unknown as StatusData);
}

async function handleReflectionReady(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as { market: "KR" | "US"; contentMd: string };
  const embed = buildReflectionEmbed(payload.market, payload.contentMd);
  const channel = await getChannel(client, "system");
  await channel?.send({ embeds: [embed] });
}

async function handleNewsSummary(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as { symbol: string; summary: string };
  const embed = buildNewsEmbed({ symbol: payload.symbol, market: event.market ?? "KR", summary: payload.summary });
  const channel = await getChannel(client, "news");
  await channel?.send({ embeds: [embed] });
}

async function handleVersionCandidateReady(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as {
    id: number;
    strategyVersion: string;
    changeSummary: string;
    backtestResult: Record<string, number>;
  };
  const lines = [
    `#${payload.id} [${event.market}] ${payload.strategyVersion}`,
    payload.changeSummary,
    `승률 ${((payload.backtestResult.win_rate ?? 0) * 100).toFixed(1)}% | ` +
      `샤프 ${(payload.backtestResult.sharpe_ratio ?? 0).toFixed(2)} | ` +
      `MDD ${((payload.backtestResult.mdd ?? 0) * 100).toFixed(2)}%`,
    "",
    `\`/version approve id:${payload.id}\` 또는 \`/version reject id:${payload.id}\``,
  ];
  const embed = buildInfoEmbed("[빈] 🧪 개선 후보 제안 — 승인 대기", lines.join("\n"));
  const channel = await getChannel(client, "system");
  await channel?.send({ embeds: [embed] });
}

async function handleMonitorAuthCode(client: Client, event: PubSubEvent): Promise<void> {
  const payload = event.payload as { code: string; ip: string; expiresInSeconds: number };
  const user = await client.users.fetch(config.developerId).catch(() => null);
  if (!user) {
    console.error("monitor_auth_dm_failed", "developer user fetch failed");
    return;
  }
  const embed = buildMonitorAuthCodeEmbed(payload.code, payload.ip, payload.expiresInSeconds);
  await user.send({ embeds: [embed] }).catch((err) => console.error("monitor_auth_dm_failed", err));
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
    case "reflection_ready":
      await handleReflectionReady(client, event);
      break;
    case "news_summary":
      await handleNewsSummary(client, event);
      break;
    case "version_candidate_ready":
      await handleVersionCandidateReady(client, event);
      break;
    case "backtest_complete":
      await handleBacktestComplete(client, event);
      break;
    case "monitor_auth_code_issued":
      await handleMonitorAuthCode(client, event);
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
