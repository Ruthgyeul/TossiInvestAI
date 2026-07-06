// #stock-analyze 리포트 Embed. 텍스트는 core/report/generator.py가 생성한 마크다운을 그대로 전달받는다.
import { EmbedBuilder } from "discord.js";

export interface ReportEmbedData {
  market: "KR" | "US" | "ALL";
  reportType: "pre_market" | "midday" | "close" | "weekly" | "on_demand";
  contentMd: string;
  chartFilePaths?: string[];
}

export function buildReportEmbed(data: ReportEmbedData): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(0x0984e3)
    .setTitle(`[빈] ${data.market} 시장 리포트`)
    .setDescription(data.contentMd.slice(0, 4000))
    .setTimestamp();
}
