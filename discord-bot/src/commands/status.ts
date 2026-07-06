// /status, /status kr|us, /holdings, /orders — 포트폴리오·보유·미체결 조회 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { buildStatusEmbed } from "../embeds/status.js";
import { getHoldings, getOrders, getStatus } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const statusData = new SlashCommandBuilder()
  .setName("status")
  .setDescription("전체 포트폴리오 현황 (KR·US 통합)")
  .addStringOption((opt) =>
    opt.setName("market").setDescription("시장별 조회").addChoices(
      { name: "KR", value: "KR" },
      { name: "US", value: "US" },
    ),
  );

async function statusExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  const market = interaction.options.getString("market") as "KR" | "US" | null;
  try {
    const status = await getStatus(market ?? undefined);
    await interaction.reply({ embeds: [buildStatusEmbed(status)] });
  } catch (err) {
    await interaction.reply({ content: `상태 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

const holdingsData = new SlashCommandBuilder().setName("holdings").setDescription("보유 종목 목록");

async function holdingsExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const { holdings } = await getHoldings();
    if (holdings.length === 0) {
      await interaction.reply("보유 종목이 없습니다.");
      return;
    }
    const lines = holdings.map((h) => {
      const price = h.market === "US" ? `$${h.currentPrice.toFixed(2)}` : `${h.currentPrice.toLocaleString()}원`;
      return `${h.symbol}(${h.market}) ${h.quantity}주 @ ${h.avgPrice.toLocaleString()} → ${price} (${(h.pnlPct * 100).toFixed(1)}%)`;
    });
    await interaction.reply(lines.join("\n"));
  } catch (err) {
    await interaction.reply({ content: `보유 종목 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

const ordersData = new SlashCommandBuilder().setName("orders").setDescription("미체결 주문 목록");

async function ordersExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const { orders } = await getOrders();
    if (orders.length === 0) {
      await interaction.reply("주문 내역이 없습니다.");
      return;
    }
    const lines = orders.map((o) => `${o.orderId} — ${o.symbol}(${o.market}) ${o.status}`);
    await interaction.reply(lines.join("\n"));
  } catch (err) {
    await interaction.reply({ content: `주문 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [
  { data: statusData, execute: statusExecute },
  { data: holdingsData, execute: holdingsExecute },
  { data: ordersData, execute: ordersExecute },
];
