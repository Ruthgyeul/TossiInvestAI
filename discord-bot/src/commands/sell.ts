// /sell {symbol} {qty} [price] — 수동 매도 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("sell")
  .setDescription("수동 매도")
  .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true))
  .addIntegerOption((opt) => opt.setName("qty").setDescription("수량").setRequired(true))
  .addNumberOption((opt) => opt.setName("price").setDescription("지정가 (생략 시 시장가)"));

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
