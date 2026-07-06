// /version — 현재 전략·프롬프트 버전 (docs/BIN.md 프롬프트·전략 버전 관리)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder().setName("version").setDescription("현재 전략·프롬프트 버전 조회");

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
