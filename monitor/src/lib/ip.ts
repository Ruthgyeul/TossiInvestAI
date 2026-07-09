const PRIVATE_IPV4_CIDRS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16"];

function ipv4ToLong(ip: string): number | null {
  const parts = ip.split(".");
  if (parts.length !== 4) return null;
  let n = 0;
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const octet = Number(part);
    if (octet < 0 || octet > 255) return null;
    n = (n << 8) | octet;
  }
  return n >>> 0;
}

function isIpv4InCidr(ip: string, cidr: string): boolean {
  const [range, bitsStr] = cidr.split("/");
  const bits = Number(bitsStr);
  const ipLong = ipv4ToLong(ip);
  const rangeLong = ipv4ToLong(range);
  if (ipLong === null || rangeLong === null || !Number.isInteger(bits) || bits < 0 || bits > 32) return false;
  if (bits === 0) return true;
  const mask = bits === 32 ? 0xffffffff : (~0 << (32 - bits)) >>> 0;
  return (ipLong & mask) === (rangeLong & mask);
}

function isPrivateIpv6(ip: string): boolean {
  const normalized = ip.toLowerCase();
  if (normalized === "::1") return true; // loopback
  if (normalized.startsWith("fc") || normalized.startsWith("fd")) return true; // unique local fc00::/7
  if (normalized.startsWith("fe80")) return true; // link-local fe80::/10
  return false;
}

/** Strips IPv6 zone id, unwraps "[...]"/":port" wrapping, and unwraps IPv4-mapped IPv6 ("::ffff:1.2.3.4"). */
export function normalizeIp(raw: string): string {
  let ip = raw.trim();
  if (ip.startsWith("[")) {
    const closeIdx = ip.indexOf("]");
    if (closeIdx !== -1) ip = ip.slice(1, closeIdx);
  } else {
    const parts = ip.split(":");
    if (parts.length === 2 && /^\d+$/.test(parts[1]) && ipv4ToLong(parts[0]) !== null) {
      ip = parts[0];
    }
  }
  ip = ip.split("%")[0];
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(ip);
  if (mapped) ip = mapped[1];
  return ip;
}

function parseTrustedCidrs(): string[] {
  return (process.env.MONITOR_TRUSTED_CIDRS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** RFC1918/loopback/link-local by default, plus any extra CIDRs from MONITOR_TRUSTED_CIDRS (IPv4 only). */
export function isInternalIp(rawIp: string): boolean {
  const ip = normalizeIp(rawIp);
  if (!ip || ip === "unknown") return false;

  if (ip.includes(":")) {
    return isPrivateIpv6(ip);
  }
  if (PRIVATE_IPV4_CIDRS.some((cidr) => isIpv4InCidr(ip, cidr))) return true;
  return parseTrustedCidrs().some((cidr) => isIpv4InCidr(ip, cidr));
}

/**
 * Next.js's Node server fills `x-forwarded-for` from the raw socket address when the
 * header is absent (see base-server.js), so this is reliable for direct exposure. If a
 * reverse proxy sits in front, it must overwrite (not merely append to) this header with
 * the real connecting IP — otherwise a client can forge it. See monitor/README.md.
 */
export function getClientIp(request: { headers: Headers }): string {
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) {
    const parts = forwardedFor
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length > 0) return normalizeIp(parts[parts.length - 1]);
  }
  const realIp = request.headers.get("x-real-ip");
  if (realIp) return normalizeIp(realIp);
  return "unknown";
}
