// 봇 진입점. Discord.js 클라이언트를 기동하고 슬래시 명령어·이벤트를 등록한다.
import "dotenv/config";
import { Client, GatewayIntentBits, Interaction } from "discord.js";

import { commandMap } from "./commands/index.js";
import { config } from "./config.js";
import { buildErrorEmbed } from "./embeds/info.js";
import { onReady } from "./events/ready.js";
import { subscribeToEvents } from "./lib/eventSubscriber.js";
import { recordServiceStarted } from "./lib/serviceHeartbeat.js";

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages],
});

client.once("ready", () => {
  onReady(client)
    .then(() => subscribeToEvents(client))
    .then(() => recordServiceStarted())
    .catch((err) => console.error("[빈] ready 처리 실패", err));
});

client.on("interactionCreate", async (interaction: Interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const command = commandMap.get(interaction.commandName);
  if (!command) return;

  // 이 봇은 단일 개발자 전용이다 — 길드 권한 설정과 무관하게 DISCORD_DEVELOPER_ID와
  // 일치하지 않는 사용자의 명령은 어떤 명령이든 여기서 차단한다 (config.ts 참고).
  if (interaction.user.id !== config.developerId) {
    const embed = buildErrorEmbed("[빈] ⛔ 권한 없음", "이 봇은 등록된 개발자만 사용할 수 있습니다.");
    await interaction.reply({ embeds: [embed], ephemeral: true }).catch(() => undefined);
    return;
  }

  try {
    await command.execute(interaction);
  } catch (err) {
    console.error(`[빈] /${interaction.commandName} 실행 실패`, err);
    const embed = buildErrorEmbed("[빈] ⚠️ 명령 처리 실패", "명령 처리 중 오류가 발생했습니다.");
    if (interaction.replied || interaction.deferred) {
      await interaction.followUp({ embeds: [embed], ephemeral: true }).catch(() => undefined);
    } else {
      await interaction.reply({ embeds: [embed], ephemeral: true }).catch(() => undefined);
    }
  }
});

client.login(config.token).catch((err) => {
  console.error("[빈] Discord 로그인 실패", err);
  process.exitCode = 1;
});
