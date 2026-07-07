// /resume — 자동매매 재개, 개발자 확인 필요 (docs/SAFETY.md "재개는 /resume 명령 + 개발자 확인 필요")
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonInteraction,
  ButtonStyle,
  ChatInputCommandInteraction,
  ComponentType,
  PermissionFlagsBits,
  SlashCommandBuilder,
} from "discord.js";

import { buildErrorEmbed, buildInfoEmbed } from "../embeds/info.js";
import { resumeTrading } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const CONFIRM_TIMEOUT_MS = 30_000;
const CONFIRM_ID = "resume-confirm";
const CANCEL_ID = "resume-cancel";

const data = new SlashCommandBuilder()
  .setName("resume")
  .setDescription("자동매매 재개")
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const confirmRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(CONFIRM_ID).setLabel("재개 확인").setStyle(ButtonStyle.Danger),
    new ButtonBuilder().setCustomId(CANCEL_ID).setLabel("취소").setStyle(ButtonStyle.Secondary),
  );

  const message = await interaction.reply({
    embeds: [
      buildInfoEmbed(
        "[빈] ▶️ 자동매매 재개 확인",
        `${interaction.user} 개발자 확인이 필요합니다. ${CONFIRM_TIMEOUT_MS / 1000}초 안에 "재개 확인"을 눌러주세요.`,
        0xfdcb6e,
      ),
    ],
    components: [confirmRow],
    fetchReply: true,
  });

  let button: ButtonInteraction;
  try {
    button = await message.awaitMessageComponent({
      componentType: ComponentType.Button,
      time: CONFIRM_TIMEOUT_MS,
      filter: (i) => i.user.id === interaction.user.id,
    });
  } catch {
    await interaction.editReply({
      embeds: [buildErrorEmbed("[빈] ⏱️ 재개 확인 시간 초과", "자동매매를 재개하지 않았습니다.")],
      components: [],
    });
    return;
  }

  if (button.customId === CANCEL_ID) {
    await button.update({
      embeds: [buildInfoEmbed("[빈] 재개 취소", "자동매매를 재개하지 않았습니다.", 0x0984e3)],
      components: [],
    });
    return;
  }

  try {
    const result = await resumeTrading();
    const embed = result.success
      ? buildInfoEmbed("[빈] ▶️ 자동매매 재개", `${button.user}님의 확인으로 자동매매를 재개했습니다.`)
      : buildErrorEmbed("[빈] ⚠️ 재개 실패", "알 수 없는 사유");
    await button.update({ embeds: [embed], components: [] });
  } catch (err) {
    await button.update({
      embeds: [buildErrorEmbed("[빈] ⚠️ 재개 요청 실패", (err as Error).message)],
      components: [],
    });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
