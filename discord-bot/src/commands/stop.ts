// /stop, /stop kr|us — 자동매매 긴급 정지 (docs/SAFETY.md EMERGENCY_STOP)
import { ChatInputCommandInteraction, PermissionFlagsBits, SlashCommandBuilder } from "discord.js";

import { buildErrorEmbed, buildInfoEmbed } from "../embeds/info.js";
import { stopTrading } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("stop")
  .setDescription("전체 자동매매 즉시 중단")
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addStringOption((opt) =>
    opt.setName("market").setDescription("특정 시장만 중단").addChoices(
      { name: "KR", value: "KR" },
      { name: "US", value: "US" },
    ),
  );

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const market = interaction.options.getString("market") as "KR" | "US" | null;

  try {
    const result = await stopTrading(market ?? undefined);
    const embed = buildInfoEmbed(
      "[빈] 🛑 긴급 정지 완료",
      `전체: ${result.emergencyStop} / KR: ${result.krStop} / US: ${result.usStop}`,
      0xfdcb6e,
    );
    await interaction.reply({ embeds: [embed] });
  } catch (err) {
    const embed = buildErrorEmbed("[빈] ⚠️ 정지 요청 실패", (err as Error).message);
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
