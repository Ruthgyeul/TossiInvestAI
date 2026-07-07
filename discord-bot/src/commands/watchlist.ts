// /watchlist, /watchlist add|remove {symbol} — 관심 종목 관리 (docs/DISCORD.md)
import { ChatInputCommandInteraction, PermissionFlagsBits, SlashCommandBuilder } from "discord.js";

import { buildErrorEmbed, buildInfoEmbed } from "../embeds/info.js";
import { addWatchlistItem, getWatchlist, removeWatchlistItem } from "../lib/coreClient.js";
import type { BotCommand } from "./types.js";

const data = new SlashCommandBuilder()
  .setName("watchlist")
  .setDescription("관심 종목 목록")
  // add/remove는 봇이 실제로 매매를 검토할 종목 범위를 바꾼다 — 서브커맨드 단위 권한 분리가
  // 안 되므로(조회까지 포함) 명령 전체를 관리자로 제한한다.
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
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
      await interaction.reply({
        embeds: [buildInfoEmbed("[빈] ✅ 관심 종목 추가", `${symbol} (${market})`)],
      });
      return;
    }

    if (subcommand === "remove") {
      const symbol = interaction.options.getString("symbol", true);
      await removeWatchlistItem(symbol);
      await interaction.reply({ embeds: [buildInfoEmbed("[빈] 🗑️ 관심 종목 제거", symbol)] });
      return;
    }

    const { items } = await getWatchlist();
    if (items.length === 0) {
      await interaction.reply({ embeds: [buildInfoEmbed("[빈] 관심 종목", "관심 종목이 없습니다.")] });
      return;
    }
    const lines = items.map((i) => `${i.symbol}(${i.market}) — 우선순위 ${i.priority}`);
    await interaction.reply({ embeds: [buildInfoEmbed("[빈] 관심 종목", lines.join("\n"))] });
  } catch (err) {
    const embed = buildErrorEmbed("[빈] ⚠️ 관심 종목 처리 실패", (err as Error).message);
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

export const commands: BotCommand[] = [{ data, execute }];
