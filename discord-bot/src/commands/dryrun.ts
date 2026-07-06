// /dryrun on|off, /simulate on|off, /simstatus — 운영 모드 전환 (docs/SAFETY.md, docs/FUND_MANAGER.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { getSimStatus, setDryRun, setSimulate } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const dryrunData = new SlashCommandBuilder()
  .setName("dryrun")
  .setDescription("DRY_RUN 모드 전환 (개발·디버깅 전용)")
  .addStringOption((opt) =>
    opt.setName("state").setDescription("on|off").setRequired(true).addChoices(
      { name: "on", value: "on" },
      { name: "off", value: "off" },
    ),
  );

async function dryrunExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  const state = interaction.options.getString("state", true) as "on" | "off";
  try {
    const result = await setDryRun(state);
    await interaction.reply(`DRY_RUN 모드: ${result.dryRun ? "on" : "off"}`);
  } catch (err) {
    await interaction.reply({ content: `모드 전환 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

const simulateData = new SlashCommandBuilder()
  .setName("simulate")
  .setDescription("시뮬레이션 모드 전환 (실전 동일 리허설, 주문만 가상)")
  .addStringOption((opt) =>
    opt.setName("state").setDescription("on|off").setRequired(true).addChoices(
      { name: "on", value: "on" },
      { name: "off", value: "off" },
    ),
  );

async function simulateExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  const state = interaction.options.getString("state", true) as "on" | "off";
  try {
    const result = await setSimulate(state);
    await interaction.reply(`SIMULATION 모드: ${result.simulation ? "on" : "off"}`);
  } catch (err) {
    await interaction.reply({ content: `모드 전환 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

const simstatusData = new SlashCommandBuilder()
  .setName("simstatus")
  .setDescription("시뮬레이션 누적 성과 — 가상 수익률·거래 횟수·승률·MDD");

async function simstatusExecute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const s = await getSimStatus();
    const lines = [
      "[빈] 🟡 시뮬레이션 성과 리포트",
      `가상 시드         ${s.seedKrw.toLocaleString()} KRW`,
      `가상 총 자산      ${s.totalValueKrw.toLocaleString()} KRW`,
      `누적 수익률       ${(s.cumulativeReturnPct * 100).toFixed(2)}%`,
      `MDD               ${(s.mdd * 100).toFixed(2)}%`,
      `샤프 지수         ${s.sharpeRatio.toFixed(2)}`,
      `총 거래           ${s.tradeCount}회`,
      `승률              ${(s.winRate * 100).toFixed(1)}%`,
      `Safety Gate 거부  ${s.rejectionCount}회`,
      `Claude API 비용   ${s.apiCostKrw.toLocaleString()} KRW (${s.apiCallCount}회)`,
    ];
    await interaction.reply(lines.join("\n"));
  } catch (err) {
    await interaction.reply({ content: `시뮬레이션 현황 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [
  { data: dryrunData, execute: dryrunExecute },
  { data: simulateData, execute: simulateExecute },
  { data: simstatusData, execute: simstatusExecute },
];
