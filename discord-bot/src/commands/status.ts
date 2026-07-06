// /status, /status kr|us, /holdings, /orders — 포트폴리오·보유·미체결 조회 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("status")
  .setDescription("전체 포트폴리오 현황 (KR·US 통합)")
  .addStringOption((opt) =>
    opt.setName("market").setDescription("시장별 조회").addChoices(
      { name: "KR", value: "KR" },
      { name: "US", value: "US" },
    ),
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
