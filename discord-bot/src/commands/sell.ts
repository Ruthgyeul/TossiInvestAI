// /sell {symbol} {qty} [price] — 수동 매도 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { placeSellOrder } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("sell")
  .setDescription("수동 매도")
  .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true))
  .addIntegerOption((opt) => opt.setName("qty").setDescription("수량").setRequired(true))
  .addNumberOption((opt) => opt.setName("price").setDescription("지정가 (생략 시 시장가)"));

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const symbol = interaction.options.getString("symbol", true);
  const qty = interaction.options.getInteger("qty", true);
  const price = interaction.options.getNumber("price") ?? undefined;

  try {
    const result = await placeSellOrder(symbol, qty, price);
    if (!result.approved) {
      await interaction.reply(`⚠️ 매도 거부: ${result.reason ?? "알 수 없는 사유"}`);
      return;
    }
    await interaction.reply(
      `✅ 매도 접수 — ${symbol} ${qty}주 @ ${result.fillPrice?.toLocaleString() ?? "-"} (Order ID: ${result.orderId})`,
    );
  } catch (err) {
    await interaction.reply({ content: `매도 요청 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
