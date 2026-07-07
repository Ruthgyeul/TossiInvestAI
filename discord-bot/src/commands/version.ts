// /version {candidates|approve|reject|rollback} — 전략·프롬프트 버전 조회·승인·반려·롤백
// (docs/SELF_IMPROVEMENT.md 자기개선 파이프라인 — 배포는 항상 개발자 승인이 필요하다).
import { ChatInputCommandInteraction, PermissionFlagsBits, SlashCommandBuilder } from "discord.js";

import { buildErrorEmbed, buildInfoEmbed } from "../embeds/info.js";
import {
  approveVersionCandidate,
  getVersion,
  getVersionCandidates,
  rejectVersionCandidate,
  rollbackVersion,
} from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("version")
  .setDescription("전략·프롬프트 버전 관리")
  // approve/reject/rollback은 배포 상태를 바꾼다 (docs/SELF_IMPROVEMENT.md "개발자 승인 필요") —
  // 서브커맨드 단위로는 권한을 나눌 수 없어 명령 전체를 관리자로 제한한다.
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addSubcommand((sub) => sub.setName("candidates").setDescription("승인 대기 중인 개선 후보 목록"))
  .addSubcommand((sub) =>
    sub
      .setName("approve")
      .setDescription("개선 후보 승인·배포")
      .addIntegerOption((opt) => opt.setName("id").setDescription("후보 ID").setRequired(true)),
  )
  .addSubcommand((sub) =>
    sub
      .setName("reject")
      .setDescription("개선 후보 반려·폐기")
      .addIntegerOption((opt) => opt.setName("id").setDescription("후보 ID").setRequired(true)),
  )
  .addSubcommand((sub) =>
    sub
      .setName("rollback")
      .setDescription("과거에 배포된 적 있는 버전으로 즉시 복귀")
      .addStringOption((opt) => opt.setName("version").setDescription("전략 버전 (예: v1.0.0)").setRequired(true)),
  );

function formatBacktest(result: Record<string, number> | null): string {
  if (!result) return "백테스트 결과 없음";
  return (
    `승률 ${((result.win_rate ?? 0) * 100).toFixed(1)}% | ` +
    `샤프 ${(result.sharpe_ratio ?? 0).toFixed(2)} | ` +
    `MDD ${((result.mdd ?? 0) * 100).toFixed(2)}% | ` +
    `수익팩터 ${(result.profit_factor ?? 0).toFixed(2)}`
  );
}

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const subcommand = interaction.options.getSubcommand(false);
  const requestedBy = `discord:${interaction.user.tag}`;

  try {
    if (subcommand === "candidates") {
      const { candidates } = await getVersionCandidates();
      if (candidates.length === 0) {
        await interaction.reply({ embeds: [buildInfoEmbed("[빈] 개선 후보", "승인 대기 중인 후보가 없습니다.")] });
        return;
      }
      const lines = candidates.map(
        (c) =>
          `#${c.id} [${c.market}] ${c.strategyVersion} (기반: ${c.basedOn ?? "-"})\n` +
          `  ${c.changeSummary ?? "-"}\n  ${formatBacktest(c.backtestResult)}`,
      );
      await interaction.reply({ embeds: [buildInfoEmbed("[빈] 승인 대기 개선 후보", lines.join("\n\n"))] });
      return;
    }

    if (subcommand === "approve") {
      const id = interaction.options.getInteger("id", true);
      const result = await approveVersionCandidate(id, requestedBy);
      const embed = result.success
        ? buildInfoEmbed("[빈] ✅ 버전 승인·배포", `#${id} 후보를 배포했습니다.`)
        : buildErrorEmbed("[빈] ⚠️ 승인 실패", result.reason ?? "알 수 없는 사유");
      await interaction.reply({ embeds: [embed], ephemeral: !result.success });
      return;
    }

    if (subcommand === "reject") {
      const id = interaction.options.getInteger("id", true);
      const result = await rejectVersionCandidate(id);
      const embed = result.success
        ? buildInfoEmbed("[빈] 🗑️ 개선 후보 반려", `#${id} 후보를 폐기했습니다.`)
        : buildErrorEmbed("[빈] ⚠️ 반려 실패", result.reason ?? "알 수 없는 사유");
      await interaction.reply({ embeds: [embed], ephemeral: !result.success });
      return;
    }

    if (subcommand === "rollback") {
      const targetVersion = interaction.options.getString("version", true);
      const result = await rollbackVersion(targetVersion, requestedBy);
      const embed = result.success
        ? buildInfoEmbed("[빈] ⏪ 버전 롤백", `${targetVersion}로 복귀했습니다.`)
        : buildErrorEmbed("[빈] ⚠️ 롤백 실패", result.reason ?? "알 수 없는 사유");
      await interaction.reply({ embeds: [embed], ephemeral: !result.success });
      return;
    }

    const version = await getVersion();
    const embed = buildInfoEmbed(
      "[빈] 전략·프롬프트 버전",
      `전략 버전: ${version.strategyVersion} | 프롬프트 버전: ${version.promptVersion}` +
        (version.deployedAt ? ` | 배포: ${version.deployedAt}` : ""),
    );
    await interaction.reply({ embeds: [embed] });
  } catch (err) {
    const embed = buildErrorEmbed("[빈] ⚠️ 버전 명령 실패", (err as Error).message);
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
