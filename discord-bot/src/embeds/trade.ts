// 매수·매도 체결 Embed. 시뮬레이션 모드에는 🟡 [시뮬레이션] 뱃지가 붙는다 (docs/DISCORD.md, docs/SAFETY.md).
import { EmbedBuilder } from "discord.js";

import { applyBinBranding } from "./common.js";

export const TRADE_COLOR = { BUY: 0x00b894, SELL: 0xe17055 } as const;

export interface TradeEmbedData {
  symbol: string;
  symbolName: string;
  market: "KR" | "US";
  quantity: number;
  fillPrice: number;
  commissionKrw: number;
  reason: string;
  decisionId: string;
  orderId: string;
  mode: "LIVE" | "SIMULATION" | "DRY_RUN";
  realizedPnlKrw?: number;
}

export function buildBuyEmbed(data: TradeEmbedData): EmbedBuilder {
  const isSim = data.mode === "SIMULATION";
  return applyBinBranding(
    new EmbedBuilder()
      .setColor(TRADE_COLOR.BUY)
      .setTitle(isSim ? "🟡 [시뮬레이션] [빈] 매수 체결 (가상)" : "[빈] 매수 체결")
      .setDescription(`${data.symbolName} (${data.symbol}) · ${data.market === "KR" ? "한국장" : "미국장"}`)
      .addFields(
        { name: "수량", value: `${data.quantity}주`, inline: true },
        { name: isSim ? "가상 체결가" : "체결가", value: `${data.fillPrice.toLocaleString()}원`, inline: true },
        { name: "수수료", value: `${data.commissionKrw.toLocaleString()}원`, inline: true },
        { name: "판단 이유", value: data.reason },
        { name: "Decision ID", value: data.decisionId },
        { name: "Order ID", value: data.orderId },
      )
      .setTimestamp(),
  );
}

export function buildSellEmbed(data: TradeEmbedData): EmbedBuilder {
  const isSim = data.mode === "SIMULATION";
  return applyBinBranding(
    new EmbedBuilder()
      .setColor(TRADE_COLOR.SELL)
      .setTitle(isSim ? "🟡 [시뮬레이션] [빈] 매도 체결 (가상)" : "[빈] 매도 체결")
      .setDescription(`${data.symbolName} (${data.symbol}) · ${data.market === "KR" ? "한국장" : "미국장"}`)
      .addFields(
        { name: "수량", value: `${data.quantity}주`, inline: true },
        { name: isSim ? "가상 체결가" : "체결가", value: `${data.fillPrice.toLocaleString()}원`, inline: true },
        { name: "실현손익", value: `${data.realizedPnlKrw?.toLocaleString() ?? "0"}원`, inline: true },
        { name: "판단 이유", value: data.reason },
        { name: "Decision ID", value: data.decisionId },
        { name: "Order ID", value: data.orderId },
      )
      .setTimestamp(),
  );
}
