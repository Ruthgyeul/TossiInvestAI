// #stock-news 채널 — 종목 관련 뉴스 요약 Embed (docs/DISCORD.md "뉴스 수집마다").
import { EmbedBuilder } from "discord.js";

import { applyBinBranding } from "./common.js";

export function buildNewsEmbed(params: { symbol: string; market: "KR" | "US"; summary: string }): EmbedBuilder {
  return applyBinBranding(
    new EmbedBuilder()
      .setColor(0x0984e3)
      .setTitle(`[빈] 📰 ${params.symbol} 뉴스 요약`)
      .setDescription(`${params.market === "KR" ? "한국장" : "미국장"}\n\n${params.summary}`)
      .setTimestamp(),
  );
}
