// /cancel {orderId} — 미체결 주문 취소 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { cancelOrder } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("cancel")
  .setDescription("미체결 주문 취소")
  .addStringOption((opt) => opt.setName("orderid").setDescription("주문 ID").setRequired(true));

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const orderId = interaction.options.getString("orderid", true);

  try {
    const result = await cancelOrder(orderId);
    await interaction.reply(
      result.success ? `✅ 주문 취소 완료: ${orderId}` : `⚠️ 취소 실패: ${result.reason ?? "알 수 없는 사유"}`,
    );
  } catch (err) {
    await interaction.reply({ content: `취소 요청 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
