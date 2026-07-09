import crypto from "node:crypto";
import { getRedis } from "./redis";

const CODE_TTL_SECONDS = Number(process.env.MONITOR_AUTH_CODE_TTL_SECONDS ?? 300);
const CODE_COOLDOWN_SECONDS = Number(process.env.MONITOR_AUTH_CODE_COOLDOWN_SECONDS ?? 30);
const MAX_ATTEMPTS = Number(process.env.MONITOR_AUTH_MAX_ATTEMPTS ?? 3);
const SESSION_TTL_SECONDS = Number(process.env.MONITOR_SESSION_TTL_SECONDS ?? 43200);
const ATTEMPTS_COUNTER_TTL_SECONDS = 60 * 60 * 24;

export const SESSION_COOKIE = "bin_monitor_session";

const PUBSUB_CHANNEL = "pubsub:events";

const key = {
  code: () => "monitor:auth:code",
  cooldown: (ip: string) => `monitor:auth:cooldown:${ip}`,
  attempts: (ip: string) => `monitor:auth:attempts:${ip}`,
  blocked: (ip: string) => `monitor:auth:blocked:${ip}`,
};

function timingSafeEqualStr(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

export async function isIpBlocked(ip: string): Promise<boolean> {
  const redis = getRedis();
  return (await redis.get(key.blocked(ip))) !== null;
}

/**
 * Mirrors the core → discord-bot envelope (docs/INTERNAL_API.md) so discord-bot's
 * existing `pubsub:events` subscriber can dispatch this like any other event. Monitor
 * has no trading "mode", so it uses the neutral "SYSTEM" value (discord-bot only, not
 * shared with core/models.py's Mode type, since core never publishes this event).
 */
async function publishAuthCodeIssued(code: string, ip: string, expiresInSeconds: number): Promise<void> {
  const redis = getRedis();
  const envelope = {
    event_type: "monitor_auth_code_issued",
    mode: "SYSTEM",
    market: null,
    correlation_id: null,
    published_at: new Date().toISOString(),
    payload: { code, ip, expiresInSeconds },
  };
  await redis.publish(PUBSUB_CHANNEL, JSON.stringify(envelope));
}

export type RequestCodeResult = { ok: true; expiresInSeconds: number } | { ok: false; reason: "blocked" | "cooldown" };

export async function requestAuthCode(ip: string): Promise<RequestCodeResult> {
  const redis = getRedis();
  if (await isIpBlocked(ip)) return { ok: false, reason: "blocked" };

  const cooldownKey = key.cooldown(ip);
  if (await redis.get(cooldownKey)) return { ok: false, reason: "cooldown" };

  const code = crypto.randomInt(0, 1_000_000).toString().padStart(6, "0");
  await redis.set(key.code(), code, "EX", CODE_TTL_SECONDS);
  await redis.set(cooldownKey, "1", "EX", CODE_COOLDOWN_SECONDS);
  await publishAuthCodeIssued(code, ip, CODE_TTL_SECONDS);

  return { ok: true, expiresInSeconds: CODE_TTL_SECONDS };
}

export type VerifyCodeResult =
  | { ok: true; sessionCookie: string; maxAge: number }
  | { ok: false; reason: "blocked" | "invalid" | "expired"; attemptsRemaining?: number };

export async function verifyAuthCode(ip: string, submitted: string): Promise<VerifyCodeResult> {
  const redis = getRedis();
  if (await isIpBlocked(ip)) return { ok: false, reason: "blocked" };

  const stored = await redis.get(key.code());
  const isMatch = stored !== null && /^\d{6}$/.test(submitted) && timingSafeEqualStr(stored, submitted);

  if (!isMatch) {
    const attemptsKey = key.attempts(ip);
    const attempts = await redis.incr(attemptsKey);
    if (attempts === 1) {
      await redis.expire(attemptsKey, ATTEMPTS_COUNTER_TTL_SECONDS);
    }
    if (attempts >= MAX_ATTEMPTS) {
      await redis.set(key.blocked(ip), "1"); // no TTL — permanent until manually cleared
      return { ok: false, reason: "blocked" };
    }
    return {
      ok: false,
      reason: stored === null ? "expired" : "invalid",
      attemptsRemaining: Math.max(0, MAX_ATTEMPTS - attempts),
    };
  }

  await redis.del(key.attempts(ip));
  await redis.del(key.code());

  const maxAge = SESSION_TTL_SECONDS;
  const sessionCookie = signSession(ip, Date.now() + maxAge * 1000);
  return { ok: true, sessionCookie, maxAge };
}

function getSecret(): string {
  const secret = process.env.MONITOR_SESSION_SECRET;
  if (!secret) throw new Error("MONITOR_SESSION_SECRET is not set");
  return secret;
}

/** Session is bound to the requesting IP so a stolen cookie can't be replayed from elsewhere. */
export function signSession(ip: string, expiresAtMs: number): string {
  const payload = `${ip}:${expiresAtMs}`;
  const payloadB64 = Buffer.from(payload).toString("base64url");
  const sig = crypto.createHmac("sha256", getSecret()).update(payloadB64).digest("base64url");
  return `${payloadB64}.${sig}`;
}

export function verifySession(token: string | undefined, ip: string): boolean {
  if (!token) return false;
  const [payloadB64, sig] = token.split(".");
  if (!payloadB64 || !sig) return false;

  const expectedSig = crypto.createHmac("sha256", getSecret()).update(payloadB64).digest("base64url");
  if (!timingSafeEqualStr(sig, expectedSig)) return false;

  const payload = Buffer.from(payloadB64, "base64url").toString();
  const [payloadIp, expStr] = payload.split(":");
  if (payloadIp !== ip) return false;

  const expiresAtMs = Number(expStr);
  return Number.isFinite(expiresAtMs) && Date.now() < expiresAtMs;
}
