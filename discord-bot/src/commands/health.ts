// /health — 라즈베리파이 상태 (CPU·메모리·온도·디스크) (docs/LOGGING.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { getHealth } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder().setName("health").setDescription("라즈베리파이 상태 조회");

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const health = await getHealth();
    const lines = [
      `CPU     ${health.cpuPct.toFixed(1)}%`,
      `메모리  ${health.memoryPct.toFixed(1)}%`,
      `디스크  ${health.diskPct.toFixed(1)}%`,
      `온도    ${health.tempC.toFixed(1)}°C`,
      `토스 API  ${health.tossApiReachable ? "정상" : "응답 없음"}`,
    ];
    await interaction.reply(lines.join("\n"));
  } catch (err) {
    await interaction.reply({ content: `상태 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
