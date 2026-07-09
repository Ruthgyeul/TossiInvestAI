import Redis from "ioredis";

declare global {
  var __monitorRedis: Redis | undefined;
}

/** Singleton so dev hot-reload / repeated Route Handler invocations don't open new connections each time. */
export function getRedis(): Redis {
  if (!global.__monitorRedis) {
    const url = process.env.REDIS_URL;
    if (!url) throw new Error("REDIS_URL is not set");
    global.__monitorRedis = new Redis(url);
  }
  return global.__monitorRedis;
}
