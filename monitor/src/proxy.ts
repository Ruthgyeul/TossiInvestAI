import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getClientIp, isInternalIp } from "@/lib/ip";
import { isIpBlocked, verifySession, SESSION_COOKIE } from "@/lib/auth";

const PUBLIC_PATHS = new Set(["/auth"]);
const PUBLIC_API_PREFIXES = ["/api/auth/"];

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
  return PUBLIC_API_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

// 내부 IP는 그대로 통과, 외부 IP는 /auth 인증 코드 검증을 통과해야 한다 (docs/MONITOR.md
// "외부 접속 인증"). 3회 이상 실패한 외부 IP는 /auth·/api/auth/*를 포함해 전부 403이다.
export async function proxy(request: NextRequest) {
  const ip = getClientIp(request);

  if (isInternalIp(ip)) {
    return NextResponse.next();
  }

  if (await isIpBlocked(ip)) {
    return new NextResponse("Access denied.", { status: 403 });
  }

  if (isPublicPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const sessionToken = request.cookies.get(SESSION_COOKIE)?.value;
  if (verifySession(sessionToken, ip)) {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL("/auth", request.url));
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
