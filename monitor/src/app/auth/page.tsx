import type { Metadata, Viewport } from "next";
import { AuthForm } from "./AuthForm";

export const metadata: Metadata = {
  title: "BIN MONITOR — 외부 접속 인증",
  robots: { index: false, follow: false },
};

// Root layout disables pinch-zoom for the kiosk view; this page is used interactively
// from arbitrary personal devices, so restore normal zoom/scaling here.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function AuthPage() {
  return <AuthForm />;
}
