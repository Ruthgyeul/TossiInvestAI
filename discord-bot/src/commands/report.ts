// /report, /report kr|us — 즉시 리포트 생성·발송 (docs/REPORT.md)
//
// core는 202 {jobId}로 즉시 응답하고, 완료되면 report_ready pub/sub 이벤트로 #stock-analyze에
// Embed가 발송된다 (docs/INTERNAL_API.md "동기 vs 지연 응답"). 이 인터랙션은 접수만 확인한다.
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { generateReport } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("report")
  .setDescription("즉시 통합 리포트 생성·발송")
  .addStringOption((opt) =>
    opt.setName("market").setDescription("시장별 리포트").addChoices(
      { name: "KR", value: "KR" },
      { name: "US", value: "US" },
    ),
  );

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const market = (interaction.options.getString("market") as "KR" | "US" | null) ?? "ALL";
  try {
    const { jobId } = await generateReport(market);
    await interaction.reply(`📊 리포트 생성을 시작했습니다 (Job ID: ${jobId}). 완료되면 #stock-analyze에 게시됩니다.`);
  } catch (err) {
    await interaction.reply({ content: `리포트 요청 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
