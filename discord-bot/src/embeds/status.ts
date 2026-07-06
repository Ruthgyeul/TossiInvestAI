// #status 채널 고정 메시지 Embed. 최초 1회 전송 후 주기적으로 edit한다 (docs/DISCORD.md).
//
// core/fund/manager.py FundManager.get_portfolio_status()가 반환하는 PortfolioStatus와
// 필드가 매칭된다 (docs/INTERNAL_API.md `GET /api/v1/status`). 실전·시뮬레이션 포트폴리오를
// 하나의 Embed에 함께 표시한다 (docs/LOGGING.md "#status 채널에는 실전과 시뮬레이션 포트폴리오가
// 동시에 표시된다").
import { EmbedBuilder } from "discord.js";

export interface Holding {
  symbol: string;
  market: "KR" | "US";
  quantity: number;
  avgPrice: number;
  currentPrice: number;
  pnlPct: number;
}

export interface PortfolioStatus {
  totalValueKrw: number;
  todayPnlKrw: number;
  todayPnlPct: number;
  cumulativePnlKrw: number;
  cumulativePnlPct: number;
  cashBufferKrw: number;
  holdings: Holding[];
  updatedAt: string;
}

export interface StatusData {
  live: PortfolioStatus | null;
  simulation: PortfolioStatus;
}

function formatPnl(krw: number, pct: number): string {
  const sign = krw >= 0 ? "+" : "";
  return `${sign}${krw.toLocaleString()} KRW (${sign}${(pct * 100).toFixed(2)}%)`;
}

function formatHolding(h: Holding, badge = ""): string {
  const price = h.market === "US" ? `$${h.currentPrice.toFixed(2)}` : `${h.currentPrice.toLocaleString()}원`;
  const sign = h.pnlPct >= 0 ? "+" : "";
  return `  ${h.symbol}(${h.market})  ${h.quantity}주  ${price}  ${sign}${(h.pnlPct * 100).toFixed(1)}%${badge}`;
}

export function buildStatusEmbed(data: StatusData): EmbedBuilder {
  const lines: string[] = ["🟢 실전 포트폴리오"];

  if (data.live) {
    lines.push(`  💰 총 자산   ${data.live.totalValueKrw.toLocaleString()} KRW`);
    lines.push(`  📈 오늘 손익 ${formatPnl(data.live.todayPnlKrw, data.live.todayPnlPct)}`);
    lines.push(`  📊 누적 손익 ${formatPnl(data.live.cumulativePnlKrw, data.live.cumulativePnlPct)}`);
    for (const h of data.live.holdings) lines.push(formatHolding(h));
    lines.push(`  💵 현금 버퍼 ${data.live.cashBufferKrw.toLocaleString()} KRW`);
  } else {
    lines.push("  현재 없음 (SIMULATION 모드 운용 중)");
  }

  lines.push("", "🟡 시뮬레이션 포트폴리오");
  lines.push(`  💰 가상 총 자산   ${data.simulation.totalValueKrw.toLocaleString()} KRW`);
  lines.push(`  📈 오늘 가상 손익 ${formatPnl(data.simulation.todayPnlKrw, data.simulation.todayPnlPct)}`);
  lines.push(`  📊 누적 가상 수익 ${formatPnl(data.simulation.cumulativePnlKrw, data.simulation.cumulativePnlPct)}`);
  for (const h of data.simulation.holdings) lines.push(formatHolding(h, "  [SIM]"));
  lines.push(`  💵 가상 현금 버퍼 ${data.simulation.cashBufferKrw.toLocaleString()} KRW`);

  const updatedAt = new Date(data.simulation.updatedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  lines.push(`  🔄 마지막 업데이트  ${updatedAt} KST`);

  return new EmbedBuilder()
    .setColor(0x0984e3)
    .setTitle("[빈] 포트폴리오 현황")
    .setDescription(lines.join("\n"))
    .setTimestamp();
}
