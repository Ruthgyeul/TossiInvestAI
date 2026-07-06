// 모든 설정은 이 파일에서만 로드한다. 소스코드에 채널 ID·토큰 하드코딩 금지 (docs/DISCORD.md).
export const config = {
  token: process.env.DISCORD_BOT_TOKEN!,
  guildId: process.env.DISCORD_GUILD_ID!,
  channels: {
    status: process.env.DISCORD_STATUS_CHANNEL_ID!,
    analyze: process.env.DISCORD_ANALYZE_CHANNEL_ID!,
    buy: process.env.DISCORD_BUY_CHANNEL_ID!,
    sell: process.env.DISCORD_SELL_CHANNEL_ID!,
    system: process.env.DISCORD_SYSTEM_CHANNEL_ID!,
    error: process.env.DISCORD_ERROR_CHANNEL_ID!,
    news: process.env.DISCORD_NEWS_CHANNEL_ID!,
    log: process.env.DISCORD_LOG_CHANNEL_ID!,
  },
  core: {
    apiUrl: process.env.CORE_INTERNAL_API_URL!,
    apiToken: process.env.CORE_INTERNAL_API_TOKEN!,
  },
  botAvatarUrl: process.env.BOT_AVATAR_URL ?? "",
} as const;
