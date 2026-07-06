// #status 채널의 고정 Embed 메시지를 관리한다. 최초 1개 전송 후 동일 메시지를 계속 edit한다
// (docs/DISCORD.md "#status 채널 운영 방식").
import { Client } from "discord.js";

import { buildStatusEmbed, StatusData } from "../embeds/status.js";
import { getChannel } from "./channels.js";

let statusMessageId: string | null = null;

/** 봇 재시작으로 메모리가 초기화돼도 "고정 메시지 1개 유지"가 깨지지 않도록, #status
 * 채널에서 봇 자신이 보낸 가장 최근 메시지를 찾아 재사용한다 (index.ts ready 이벤트에서 1회 호출). */
export async function restoreStatusMessageId(client: Client): Promise<void> {
  const channel = await getChannel(client, "status");
  if (!channel || !client.user) return;

  try {
    const recent = await channel.messages.fetch({ limit: 20 });
    const lastOwn = recent.find((m) => m.author.id === client.user!.id);
    if (lastOwn) {
      statusMessageId = lastOwn.id;
    }
  } catch (err) {
    console.error("status_message_restore_failed", err);
  }
}

export async function updateStatusEmbed(client: Client, data: StatusData): Promise<void> {
  const channel = await getChannel(client, "status");
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
