import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getClientIp, maskIpForDisplay } from "@/lib/ip";
import { requestAuthCode, MAX_ATTEMPTS } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const ip = getClientIp(request);
  const result = await requestAuthCode(ip);

  if (!result.ok) {
    const status = result.reason === "blocked" ? 403 : 429;
    return NextResponse.json({ ok: false, reason: result.reason }, { status });
  }

  return NextResponse.json({
    ok: true,
    expiresInSeconds: result.expiresInSeconds,
    maxAttempts: MAX_ATTEMPTS,
    maskedIp: maskIpForDisplay(ip),
  });
}
