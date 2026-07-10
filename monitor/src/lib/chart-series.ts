export interface ChartSeries {
  /** SVG path for the cumulative-return line ("누적" in the legend). */
  cumPath: string;
  /** SVG path for the benchmark line ("벤치마크") — null when the period has no benchmark data. */
  benchPath: string | null;
  /** SVG path for the drawdown fill ("낙폭") — the area between the running peak and the cumulative line. */
  ddPath: string;
}

/**
 * Turns a bar-delta series into the three overlay paths drawn on top of the bar chart —
 * ports the source design's `buildSeries()`. `viewBox="0 0 1000 100"` on the `<svg>` is
 * assumed by callers; `x`/`y` here are pre-formatted for that box.
 */
export function buildChartSeries(bars: number[], benchmarkBars: number[]): ChartSeries {
  const n = bars.length;
  if (n === 0) {
    return { cumPath: "", benchPath: null, ddPath: "" };
  }

  const width = 1000;
  let cum = 0;
  const cumVals = bars.map((v) => {
    cum += v;
    return cum;
  });

  const hasBenchmark = benchmarkBars.length === n;
  let benchCumVals: number[] | null = null;
  if (hasBenchmark) {
    let benchCum = 0;
    benchCumVals = benchmarkBars.map((v) => {
      benchCum += v;
      return benchCum;
    });
  }

  const maxAbs = Math.max(
    ...cumVals.map(Math.abs),
    ...(benchCumVals ? benchCumVals.map(Math.abs) : []),
    1,
  );
  const scale = 40 / maxAbs;
  const x = (i: number) => (((i + 0.5) / n) * width).toFixed(1);
  const toPath = (ys: string[]) => ys.map((y, i) => `${i === 0 ? "M" : "L"}${x(i)},${y}`).join(" ");

  const cumY = cumVals.map((c) => (50 - c * scale).toFixed(1));
  const cumPath = toPath(cumY);

  let benchPath: string | null = null;
  if (benchCumVals) {
    const benchY = benchCumVals.map((c) => (50 - c * scale).toFixed(1));
    benchPath = toPath(benchY);
  }

  let peak = -Infinity;
  const peakY = cumVals.map((c) => {
    peak = Math.max(peak, c);
    return (50 - peak * scale).toFixed(1);
  });
  let ddPath = peakY.map((y, i) => `${i === 0 ? "M" : "L"}${x(i)},${y}`).join(" ");
  ddPath += ` ${cumY
    .slice()
    .reverse()
    .map((y, i) => `L${x(n - 1 - i)},${y}`)
    .join(" ")} Z`;

  return { cumPath, benchPath, ddPath };
}
