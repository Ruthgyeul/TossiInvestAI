// 봇 진입점. Discord.js 클라이언트를 기동하고 슬래시 명령어·이벤트를 등록한다.
import "dotenv/config";
import { Client, GatewayIntentBits } from "discord.js";

import { config } from "./config.js";

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages],
});

client.once("ready", () => {
  console.log(`[빈] Discord 봇 로그인 완료: ${client.user?.tag}`);
});

client.login(config.token);
