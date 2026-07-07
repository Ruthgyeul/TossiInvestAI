// /sell {symbol} {qty} [price] — 수동 매도 (docs/DISCORD.md)
import { ChatInputCommandInteraction, PermissionFlagsBits, SlashCommandBuilder } from "discord.js";

import { buildErrorEmbed, buildInfoEmbed } from "../embeds/info.js";
import { placeSellOrder } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("sell")
  .setDescription("수동 매도")
  // 실제 자금이 움직이는 명령이므로 기본값을 관리자로 제한한다 (buy.ts와 동일 이유).
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true))
  .addIntegerOption((opt) => opt.setName("qty").setDescription("수량").setRequired(true).setMinValue(1))
  .addNumberOption((opt) =>
    opt.setName("price").setDescription("지정가 (생략 시 시장가)").setMinValue(0.01),
  );

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const symbol = interaction.options.getString("symbol", true);
  const qty = interaction.options.getInteger("qty", true);
  const price = interaction.options.getNumber("price") ?? undefined;

  try {
    const result = await placeSellOrder(symbol, qty, price);
    if (!result.approved) {
      const embed = buildErrorEmbed("[빈] ⚠️ 매도 거부", result.reason ?? "알 수 없는 사유");
      await interaction.reply({ embeds: [embed] });
      return;
    }
    const embed = buildInfoEmbed(
      "[빈] ✅ 매도 접수",
      `${symbol} ${qty}주 @ ${result.fillPrice?.toLocaleString() ?? "-"} (Order ID: ${result.orderId})`,
    );
    await interaction.reply({ embeds: [embed] });
  } catch (err) {
    const embed = buildErrorEmbed("[빈] ⚠️ 매도 요청 실패", (err as Error).message);
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
