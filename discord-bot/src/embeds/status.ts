// #status 채널 고정 메시지 Embed. 최초 1회 전송 후 주기적으로 edit한다 (docs/DISCORD.md).
import { EmbedBuilder } from "discord.js";

export interface Holding {
  symbol: string;
  symbolName: string;
  quantity: number;
  price: number;
  changePct: number;
  currency: "KRW" | "USD";
}

export interface PortfolioStatus {
  totalValueKrw: number;
  todayPnlKrw: number;
  todayPnlPct: number;
  cumulativePnlKrw: number;
  cumulativePnlPct: number;
  krHoldings: Holding[];
  usHoldings: Holding[];
  cashBufferKrw: number;
  isSimulation: boolean;
}

export function buildStatusEmbed(status: PortfolioStatus): EmbedBuilder {
  const badge = status.isSimulation ? "🟡 시뮬레이션 " : "";
  return new EmbedBuilder()
    .setColor(0x0984e3)
    .setTitle(`[빈] ${badge}포트폴리오 현황`)
    .addFields(
      { name: "💰 총 자산", value: `${status.totalValueKrw.toLocaleString()} KRW` },
      { name: "📈 오늘 손익", value: `${status.todayPnlKrw.toLocaleString()} KRW (${status.todayPnlPct.toFixed(2)}%)` },
      { name: "📊 누적 손익", value: `${status.cumulativePnlKrw.toLocaleString()} KRW (${status.cumulativePnlPct.toFixed(2)}%)` },
      { name: "💵 현금 버퍼", value: `${status.cashBufferKrw.toLocaleString()} KRW` },
    )
    .setTimestamp();
}
