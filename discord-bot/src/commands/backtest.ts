// /backtest {strategy} {period} — 백테스트 실행 (1Y/3Y/5Y) (docs/BIN.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("backtest")
  .setDescription("백테스트 실행")
  .addStringOption((opt) => opt.setName("strategy").setDescription("전략 이름").setRequired(true))
  .addStringOption((opt) =>
    opt.setName("period").setDescription("기간").setRequired(true).addChoices(
      { name: "1Y", value: "1Y" },
      { name: "3Y", value: "3Y" },
      { name: "5Y", value: "5Y" },
    ),
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
