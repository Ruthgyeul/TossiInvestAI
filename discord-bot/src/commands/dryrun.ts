// /dryrun on|off, /simulate on|off, /simstatus — 운영 모드 전환 (docs/SAFETY.md, docs/FUND_MANAGER.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("dryrun")
  .setDescription("DRY_RUN 모드 전환 (개발·디버깅 전용)")
  .addStringOption((opt) =>
    opt.setName("state").setDescription("on|off").setRequired(true).addChoices(
      { name: "on", value: "on" },
      { name: "off", value: "off" },
    ),
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
