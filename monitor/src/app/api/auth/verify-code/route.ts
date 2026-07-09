import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getClientIp } from "@/lib/ip";
import { verifyAuthCode, SESSION_COOKIE } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const ip = getClientIp(request);
  const body = await request.json().catch(() => null);
  const code = typeof body?.code === "string" ? body.code.trim() : "";

  const result = await verifyAuthCode(ip, code);

  if (!result.ok) {
    const status = result.reason === "blocked" ? 403 : 401;
    return NextResponse.json({ ok: false, reason: result.reason, attemptsRemaining: result.attemptsRemaining }, { status });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, result.sessionCookie, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: result.maxAge,
  });
  return response;
}
