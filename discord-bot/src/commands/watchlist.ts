// /watchlist, /watchlist add|remove {symbol} — 관심 종목 관리 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

import { addWatchlistItem, getWatchlist, removeWatchlistItem } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("watchlist")
  .setDescription("관심 종목 목록")
  .addSubcommand((sub) =>
    sub.setName("add").setDescription("관심 종목 수동 추가")
      .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true))
      .addStringOption((opt) =>
        opt.setName("market").setDescription("시장").setRequired(true).addChoices(
          { name: "KR", value: "KR" },
          { name: "US", value: "US" },
        ),
      ),
  )
  .addSubcommand((sub) =>
    sub.setName("remove").setDescription("관심 종목 제거")
      .addStringOption((opt) => opt.setName("symbol").setDescription("종목코드").setRequired(true)),
  );

async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const subcommand = interaction.options.getSubcommand(false);

  try {
    if (subcommand === "add") {
      const symbol = interaction.options.getString("symbol", true);
      const market = interaction.options.getString("market", true) as "KR" | "US";
      await addWatchlistItem(symbol, market);
      await interaction.reply(`✅ 관심 종목 추가: ${symbol} (${market})`);
      return;
    }

    if (subcommand === "remove") {
      const symbol = interaction.options.getString("symbol", true);
      await removeWatchlistItem(symbol);
      await interaction.reply(`🗑️ 관심 종목 제거: ${symbol}`);
      return;
    }

    const { items } = await getWatchlist();
    if (items.length === 0) {
      await interaction.reply("관심 종목이 없습니다.");
      return;
    }
    const lines = items.map((i) => `${i.symbol}(${i.market}) — 우선순위 ${i.priority}`);
    await interaction.reply(lines.join("\n"));
  } catch (err) {
    await interaction.reply({ content: `관심 종목 처리 실패: ${(err as Error).message}`, ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
