// #status 채널의 고정 Embed 메시지를 관리한다. 최초 1개 전송 후 동일 메시지를 계속 edit한다
// (docs/DISCORD.md "#status 채널 운영 방식").
import { Client, TextChannel } from "discord.js";

import { config } from "../config.js";
import { buildStatusEmbed, StatusData } from "../embeds/status.js";

let statusMessageId: string | null = null;

async function getStatusChannel(client: Client): Promise<TextChannel | null> {
  const channel = await client.channels.fetch(config.channels.status).catch(() => null);
  return channel instanceof TextChannel ? channel : null;
}

export async function updateStatusEmbed(client: Client, data: StatusData): Promise<void> {
  const channel = await getStatusChannel(client);
  if (!channel) return;

  const embed = buildStatusEmbed(data);

  if (statusMessageId) {
    try {
      const message = await channel.messages.fetch(statusMessageId);
      await message.edit({ embeds: [embed] });
      return;
    } catch {
      statusMessageId = null; // 메시지가 삭제됐으면 새로 전송한다
    }
  }

  const message = await channel.send({ embeds: [embed] });
  statusMessageId = message.id;
}
