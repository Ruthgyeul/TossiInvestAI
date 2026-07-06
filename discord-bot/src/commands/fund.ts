// /fund — 자금 배분 현황, /apicost — 이번 달 Claude API 비용 추정 (docs/DISCORD.md, docs/FUND_MANAGER.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { getApiCost, getFund } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const fundData = new SlashCommandBuilder()
  .setName("fund")
  .setDescription("자금 배분 현황 (슬롯별 잔고, 버퍼, 누적 수익)");

async function fundExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const f = await getFund();
    const lines = [
      `운용 자금       ${f.operatingFundsKrw.toLocaleString()} KRW`,
      `현금 버퍼       ${f.cashBufferKrw.toLocaleString()} KRW`,
      `누적 수익률     ${(f.cumulativeReturnPct * 100).toFixed(2)}%`,
      "",
      "종목별 비중:",
      ...(f.positionRatios.length
        ? f.positionRatios.map((p) => `  ${p.symbol}: ${(p.ratio * 100).toFixed(1)}%`)
        : ["  보유 종목 없음"]),
    ];
    await interaction.reply(lines.join("\n"));
  } catch (err) {
    await interaction.reply({ content: `자금 현황 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

const apicostData = new SlashCommandBuilder()
  .setName("apicost")
  .setDescription("이번 달 Claude API 사용 비용 추정");

async function apicostExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const cost = await getApiCost();
    await interaction.reply(
      `이번 달 Claude API 비용: ${cost.monthCostKrw.toLocaleString()} KRW (${cost.monthCostUsd} USD, ${cost.callCount}회 호출)`,
    );
  } catch (err) {
    await interaction.reply({ content: `API 비용 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [
  { data: fundData, execute: fundExecute },
  { data: apicostData, execute: apicostExecute },
];
