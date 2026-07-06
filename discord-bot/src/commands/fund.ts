// /fund — 자금 배분 현황, /apicost — 이번 달 Claude API 비용 추정 (docs/DISCORD.md, docs/FUND_MANAGER.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder().setName("fund").setDescription("자금 배분 현황 (슬롯별 잔고, 버퍼, 누적 수익)");

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
