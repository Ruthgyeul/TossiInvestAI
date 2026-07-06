// 클라이언트 ready 이벤트 — 슬래시 명령어 등록, #status 채널 초기 Embed 전송.
import { Client, REST, Routes } from "discord.js";

import { commands } from "../commands/index.js";
import { config } from "../config.js";
import { getStatus } from "../lib/coreClient.js";
import { updateStatusEmbed } from "../lib/statusChannel.js";

export async function onReady(client: Client): Promise<void> {
  if (!client.user) {
    throw new Error("ready 이벤트인데 client.user가 없습니다");
  }

  const rest = new REST().setToken(config.token);
  await rest.put(Routes.applicationGuildCommands(client.user.id, config.guildId), {
    body: commands.map((c) => c.data.toJSON()),
  });

  try {
    const status = await getStatus();
    await updateStatusEmbed(client, status);
  } catch (err) {
    console.error("initial_status_embed_failed", err);
  }

  console.log(`[빈] Discord 봇 로그인 완료: ${client.user.tag}`);
}
