// 모든 Embed 공통 구조 — author/footer (docs/DISCORD.md "모든 Embed는 아래 공통 구조를 따른다").
import { EmbedBuilder } from "discord.js";

import { config } from "../config.js";

const _KST_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function applyBinBranding(embed: EmbedBuilder, at: Date = new Date()): EmbedBuilder {
  return embed
    .setAuthor({ name: "빈(Bin)", iconURL: config.botAvatarUrl || undefined })
    .setFooter({ text: `빈 | ${_KST_FORMATTER.format(at)} KST` });
}
