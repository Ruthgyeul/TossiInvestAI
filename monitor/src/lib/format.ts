export function formatKrw(value: number): string {
  return `₩${Math.round(value).toLocaleString("ko-KR")}`;
}

export function formatSignedKrw(value: number): string {
  const sign = value >= 0 ? "+" : "-";
  return `${sign}${Math.abs(Math.round(value)).toLocaleString("ko-KR")}`;
}

export function formatPct(value: number, decimals = 2): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}

export function formatPlainPct(value: number, decimals = 1): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}

/** "positive" | "negative" | "neutral" — drives the red/blue color modifier classes. */
export function signClass(value: number): "positive" | "negative" | "neutral" {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

/**
 * Bar height (% of the up/down half) for a day's real PnL value, scaled against the
 * largest magnitude in the visible window — auto-scaling like a real time-series chart,
 * unlike the source design's fixed 0-100 demo scale. `maxAbs` should be
 * `Math.max(...bars.map(Math.abs), 1)` from the caller so an all-zero window doesn't
 * divide by zero.
 */
export function barHeights(value: number, maxAbs: number): { pos: number; neg: number } {
  const magnitudePct = Math.min(100, (Math.abs(value) / maxAbs) * 100);
  return {
    pos: value > 0 ? magnitudePct : 4,
    neg: value < 0 ? magnitudePct : 4,
  };
}

const kstTimestampFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

/** "YYYY.MM.DD HH:mm:ss" in KST, matching the header clock's format. */
export function formatKstTimestamp(date: Date): string {
  const parts = kstTimestampFormatter.formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}.${get("month")}.${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

/** "MM:SS" countdown display, clamped to 0. */
export function formatCountdown(totalSeconds: number): string {
  const clamped = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(clamped / 60);
  const seconds = clamped % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
