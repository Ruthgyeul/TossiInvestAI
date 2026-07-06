// 슬래시 커맨드 응답 공용 Embed — CLAUDE.md 규칙 7 "Discord 메시지는 모두 Embed 형식으로 전송한다".
import { EmbedBuilder } from "discord.js";

import { applyBinBranding } from "./common.js";

export function buildInfoEmbed(title: string, description: string, color = 0x0984e3): EmbedBuilder {
  return applyBinBranding(
    new EmbedBuilder().setColor(color).setTitle(title).setDescription(description).setTimestamp(),
  );
}

export function buildErrorEmbed(title: string, message: string): EmbedBuilder {
  return applyBinBranding(
    new EmbedBuilder().setColor(0xd63031).setTitle(title).setDescription(message).setTimestamp(),
  );
}
