// /watchlist, /watchlist add|remove {symbol} — 관심 종목 관리 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("watchlist")
  .setDescription("관심 종목 목록")
  .addSubcommand((sub) =>
    sub.setName("add").setDescription("관심 종목 수동 추가")
      .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true)),
  )
  .addSubcommand((sub) =>
    sub.setName("remove").setDescription("관심 종목 제거")
      .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true)),
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
