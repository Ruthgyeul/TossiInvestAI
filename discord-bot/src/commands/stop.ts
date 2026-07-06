// /stop, /stop kr|us — 자동매매 긴급 정지 (docs/SAFETY.md EMERGENCY_STOP)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("stop")
  .setDescription("전체 자동매매 즉시 중단")
  .addStringOption((opt) =>
    opt.setName("market").setDescription("특정 시장만 중단").addChoices(
      { name: "KR", value: "KR" },
      { name: "US", value: "US" },
    ),
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
