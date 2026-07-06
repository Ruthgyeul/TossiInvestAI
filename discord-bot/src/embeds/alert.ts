// #stock-error / #stock-system 경고·거부·긴급정지 Embed (docs/DISCORD.md, docs/SAFETY.md).
import { EmbedBuilder } from "discord.js";

export function buildSafetyRejectionEmbed(params: {
  symbolName: string;
  symbol: string;
  attempted: string;
  reason: string;
  isSimulation: boolean;
}): EmbedBuilder {
  const badge = params.isSimulation ? "🟡 [시뮬레이션] " : "";
  return new EmbedBuilder()
    .setColor(0xd63031)
    .setTitle(`${badge}[빈] ⚠️ 주문 거부`)
    .addFields(
      { name: "종목", value: `${params.symbolName} (${params.symbol})` },
      { name: "시도", value: params.attempted },
      { name: "거부 사유", value: params.reason },
    )
    .setTimestamp();
}

export function buildEmergencyStopEmbed(market?: "KR" | "US"): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(0xfdcb6e)
    .setTitle("[빈] 🛑 긴급 정지")
    .setDescription(market ? `${market} 시장 자동매매가 중단되었습니다.` : "전체 자동매매가 중단되었습니다.")
    .setTimestamp();
}

export function buildHealthAlertEmbed(message: string): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(0xd63031)
    .setTitle("[빈] ⚠️ 시스템 경고")
    .setDescription(message)
    .setTimestamp();
}
