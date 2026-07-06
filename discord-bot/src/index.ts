// 봇 진입점. Discord.js 클라이언트를 기동하고 슬래시 명령어·이벤트를 등록한다.
import "dotenv/config";
import { Client, GatewayIntentBits, Interaction } from "discord.js";

import { commandMap } from "./commands/index.js";
import { config } from "./config.js";
import { onReady } from "./events/ready.js";
import { subscribeToEvents } from "./lib/eventSubscriber.js";

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages],
});

client.once("ready", () => {
  onReady(client)
    .then(() => subscribeToEvents(client))
    .catch((err) => console.error("[빈] ready 처리 실패", err));
});

client.on("interactionCreate", async (interaction: Interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const command = commandMap.get(interaction.commandName);
  if (!command) return;

  try {
    await command.execute(interaction);
  } catch (err) {
    console.error(`[빈] /${interaction.commandName} 실행 실패`, err);
    const errorMessage = "명령 처리 중 오류가 발생했습니다.";
    if (interaction.replied || interaction.deferred) {
      await interaction.followUp({ content: errorMessage, ephemeral: true }).catch(() => undefined);
    } else {
      await interaction.reply({ content: errorMessage, ephemeral: true }).catch(() => undefined);
    }
  }
});

client.login(config.token).catch((err) => {
  console.error("[빈] Discord 로그인 실패", err);
  process.exitCode = 1;
});
