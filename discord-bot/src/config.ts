// 모든 설정은 이 파일에서만 로드한다. 소스코드에 채널 ID·토큰 하드코딩 금지 (docs/DISCORD.md).
export const config = {
  token: process.env.DISCORD_BOT_TOKEN!,
  guildId: process.env.DISCORD_GUILD_ID!,
  // 이 봇은 단일 개발자 전용이다 — Discord 길드 권한(Administrator 등)과 별개로,
  // index.ts의 interactionCreate 핸들러가 이 ID와 일치하는 사용자의 명령만 실행한다.
  developerId: process.env.DISCORD_DEVELOPER_ID!,
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
  // core와 동일한 라즈베리파이의 Redis — pubsub:events 구독 전용 (docs/INTERNAL_API.md).
  redisUrl: process.env.REDIS_URL!,
  botAvatarUrl: process.env.BOT_AVATAR_URL ?? "",
} as const;
