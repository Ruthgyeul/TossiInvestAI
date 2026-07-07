// /cancel {orderId} — 미체결 주문 취소 (docs/DISCORD.md)
import { ChatInputCommandInteraction, PermissionFlagsBits, SlashCommandBuilder } from "discord.js";

import { buildErrorEmbed, buildInfoEmbed } from "../embeds/info.js";
import { cancelOrder } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("cancel")
  .setDescription("미체결 주문 취소")
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addStringOption((opt) => opt.setName("orderid").setDescription("주문 ID").setRequired(true));

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const orderId = interaction.options.getString("orderid", true);

  try {
    const result = await cancelOrder(orderId);
    const embed = result.success
      ? buildInfoEmbed("[빈] ✅ 주문 취소 완료", orderId)
      : buildErrorEmbed("[빈] ⚠️ 취소 실패", result.reason ?? "알 수 없는 사유");
    await interaction.reply({ embeds: [embed] });
  } catch (err) {
    const embed = buildErrorEmbed("[빈] ⚠️ 취소 요청 실패", (err as Error).message);
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
