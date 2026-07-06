// /resume — 자동매매 재개, 개발자 확인 필요 (docs/SAFETY.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { resumeTrading } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder().setName("resume").setDescription("자동매매 재개");

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  try {
    const result = await resumeTrading();
    await interaction.reply(result.success ? "▶️ 자동매매를 재개했습니다." : "⚠️ 재개 실패");
  } catch (err) {
    await interaction.reply({ content: `재개 요청 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
