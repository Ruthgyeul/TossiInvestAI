// /report, /report kr|us — 즉시 리포트 생성·발송 (docs/REPORT.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("report")
  .setDescription("즉시 통합 리포트 생성·발송")
  .addStringOption((opt) =>
    opt.setName("market").setDescription("시장별 리포트").addChoices(
      { name: "KR", value: "KR" },
      { name: "US", value: "US" },
    ),
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
