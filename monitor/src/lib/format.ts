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

/** Mirrors the source design's bar-height formula: 50 is flat, values further from 50 grow taller. */
export function barHeights(value: number): { pos: number; neg: number } {
  return {
    pos: value > 50 ? (value - 50) * 2 : 4,
    neg: value <= 50 ? (50 - value) * 2 : 4,
  };
}
