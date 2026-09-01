// Pure statistical helpers for the Statistiques Avancées tool. No DOM, no
// Chart.js — kept separate so the math is easy to audit and to unit-test.

export interface QuartileSummary {
  n: number;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  iqr: number;
  lowerFence: number;
  upperFence: number;
  outliers: number[];
  mean: number;
  stdDev: number;
}

// Linear-interpolation quantile (Type 7 / R's default) — standard choice for
// box plots and matches what most stats software reports.
function quantile(sorted: number[], p: number): number {
  if (sorted.length === 1) return sorted[0];
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

export function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

// Sample standard deviation (n-1 denominator) — values here are always a
// sample of countries, never the full population of interest.
export function stdDev(values: number[]): number {
  if (values.length < 2) return 0;
  const m = mean(values);
  return Math.sqrt(values.reduce((s, v) => s + (v - m) ** 2, 0) / (values.length - 1));
}

export function summarize(values: number[]): QuartileSummary {
  const sorted = [...values].sort((a, b) => a - b);
  const q1 = quantile(sorted, 0.25);
  const median = quantile(sorted, 0.5);
  const q3 = quantile(sorted, 0.75);
  const iqr = q3 - q1;
  const lowerFence = q1 - 1.5 * iqr;
  const upperFence = q3 + 1.5 * iqr;
  const outliers = sorted.filter((v) => v < lowerFence || v > upperFence);
  return {
    n: sorted.length,
    min: sorted[0],
    q1,
    median,
    q3,
    max: sorted[sorted.length - 1],
    iqr,
    lowerFence,
    upperFence,
    outliers,
    mean: mean(sorted),
    stdDev: stdDev(sorted),
  };
}

export function pearson(xs: number[], ys: number[]): number {
  const n = xs.length;
  if (n < 2) return 0;
  const mx = mean(xs);
  const my = mean(ys);
  let num = 0;
  let dx2 = 0;
  let dy2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    num += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const denom = Math.sqrt(dx2 * dy2);
  return denom === 0 ? 0 : num / denom;
}

export interface Regression {
  slope: number;
  intercept: number;
  r: number;
  r2: number;
}

export function linearRegression(xs: number[], ys: number[]): Regression {
  const n = xs.length;
  const mx = mean(xs);
  const my = mean(ys);
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  const slope = den === 0 ? 0 : num / den;
  const intercept = my - slope * mx;
  const r = pearson(xs, ys);
  return { slope, intercept, r, r2: r * r };
}

// Sturges' rule: a standard, well-established default for histogram bin
// count that avoids both over- and under-smoothing for typical sample sizes
// (here, up to 54 countries).
export function sturgesBinCount(n: number): number {
  return Math.max(1, Math.ceil(Math.log2(n) + 1));
}

export interface Histogram {
  edges: number[];
  counts: number[];
}

export function histogram(values: number[], binCount = sturgesBinCount(values.length)): Histogram {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = (max - min) / binCount || 1;
  const edges = Array.from({ length: binCount + 1 }, (_, i) => min + i * width);
  const counts = new Array(binCount).fill(0);
  for (const v of values) {
    let idx = width === 0 ? 0 : Math.floor((v - min) / width);
    if (idx >= binCount) idx = binCount - 1;
    if (idx < 0) idx = 0;
    counts[idx]++;
  }
  return { edges, counts };
}

// Gaussian KDE with Silverman's rule-of-thumb bandwidth — used for the
// violin plot's density curve.
export function kde(values: number[], points: number[]): number[] {
  const n = values.length;
  const sd = stdDev(values) || 1;
  const bandwidth = 1.06 * sd * Math.pow(n, -1 / 5) || 1;
  return points.map((x) => {
    const sum = values.reduce((s, v) => {
      const u = (x - v) / bandwidth;
      return s + Math.exp(-0.5 * u * u);
    }, 0);
    return sum / (n * bandwidth * Math.sqrt(2 * Math.PI));
  });
}

// Pairwise-deletion Pearson correlation matrix: for each pair of
// indicators, uses only the countries that have a value for both (rather
// than dropping a country from the whole matrix for one missing value).
export function correlationMatrix(valuesByKey: Record<string, Record<string, number>>): { keys: string[]; matrix: number[][]; sampleSizes: number[][] } {
  const keys = Object.keys(valuesByKey);
  const n = keys.length;
  const matrix: number[][] = Array.from({ length: n }, () => new Array(n).fill(0));
  const sampleSizes: number[][] = Array.from({ length: n }, () => new Array(n).fill(0));
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) {
        matrix[i][j] = 1;
        sampleSizes[i][j] = Object.keys(valuesByKey[keys[i]]).length;
        continue;
      }
      const a = valuesByKey[keys[i]];
      const b = valuesByKey[keys[j]];
      const common = Object.keys(a).filter((iso3) => b[iso3] != null);
      sampleSizes[i][j] = common.length;
      matrix[i][j] = common.length < 3 ? NaN : pearson(common.map((c) => a[c]), common.map((c) => b[c]));
    }
  }
  return { keys, matrix, sampleSizes };
}
