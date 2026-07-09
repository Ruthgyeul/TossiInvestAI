// BIN MONITOR 외부 접속 인증 코드 DM (docs/MONITOR.md "외부 접속 인증"). 채널이 아니라
// DISCORD_DEVELOPER_ID에게 직접 DM으로 전송된다 — 절대 길드 채널에 게시하지 않는다.
import { EmbedBuilder } from "discord.js";

import { applyBinBranding } from "./common.js";

export function buildMonitorAuthCodeEmbed(code: string, ip: string, expiresInSeconds: number): EmbedBuilder {
  const minutes = Math.round(expiresInSeconds / 60);
  return applyBinBranding(
    new EmbedBuilder()
      .setColor(0x0984e3)
      .setTitle("[빈] 🔐 모니터 외부 접속 인증 코드")
      .addFields(
        { name: "인증 코드", value: `\`${code}\`` },
        { name: "요청 IP", value: ip },
        { name: "유효 시간", value: `${minutes}분` },
      )
      .setTimestamp(),
  );
}
