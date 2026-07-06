// /version — 현재 전략·프롬프트 버전 (docs/BIN.md 프롬프트·전략 버전 관리)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { getVersion } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder().setName("version").setDescription("현재 전략·프롬프트 버전 조회");

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const version = await getVersion();
    await interaction.reply(
      `전략 버전: ${version.strategyVersion} | 프롬프트 버전: ${version.promptVersion}` +
        (version.deployedAt ? ` | 배포: ${version.deployedAt}` : ""),
    );
  } catch (err) {
    await interaction.reply({ content: `버전 조회 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
