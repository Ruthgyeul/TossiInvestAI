// /resume — 자동매매 재개, 개발자 확인 필요 (docs/SAFETY.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder().setName("resume").setDescription("자동매매 재개");

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
