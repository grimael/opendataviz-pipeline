import { Chart } from "chart.js";
import { isDark } from "./theme";

Chart.defaults.font.family = "Inter, ui-sans-serif, system-ui, sans-serif";

// Broad categorical palette for multi-series charts (compare, rankings bars) —
// led by the OpenDataViz accent (cyan), then the pole accents, then tints of
// the same family so it never has to reach outside the brand palette.
export const COLORS = [
  "#00D4FF", "#FF6B35", "#00E676", "#0077BE", "#FFAB00", "#1A3A5C",
  "#FF1744", "#5CE6F5", "#FFA36B", "#5CEBA8", "#4FB3E8", "#0A1628",
];

// Per-pole accent, matches the CSS custom properties in global.css.
export const POLE_COLORS: Record<string, string> = {
  Economy: "#ff6b35",
  Health: "#1a3a5c",
  Education: "#00d4ff",
  Infrastructure: "#0077be",
};

export function textColor(): string {
  return isDark() ? "#a99b87" : "#5a6c7d";
}
export function gridColor(): string {
  return isDark() ? "#322b3d" : "#dbe4f0";
}

export function barOpts() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: "y" as const,
    scales: {
      x: { ticks: { color: textColor() }, grid: { color: gridColor() } },
      y: { ticks: { color: textColor(), font: { size: 11 } }, grid: { display: false } },
    },
    plugins: { legend: { display: false } },
  };
}

export function lineOpts() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    // Extra bottom room + a cap on how many x-axis labels can appear at once:
    // 25 rotated year labels packed into a narrow card overlap each other
    // badly enough that the leading digit of each year reads as clipped.
    layout: { padding: { bottom: 32, top: 8, left: 4, right: 12 } },
    scales: {
      x: {
        // Never rotated: a diagonal label at small font size is what read as
        // "truncated" (overlapping neighbours). Horizontal-only + autoSkip
        // means Chart.js just shows fewer labels rather than tilting them.
        ticks: { color: textColor(), autoSkip: true, maxTicksLimit: 8, maxRotation: 0, minRotation: 0, font: { size: 13 } },
        grid: { color: gridColor() },
      },
      y: { ticks: { color: textColor(), font: { size: 13 } }, grid: { color: gridColor() } },
    },
    plugins: { legend: { labels: { color: textColor(), font: { size: 13 } } } },
  };
}

export function donutOpts() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "68%",
    plugins: {
      legend: { position: "bottom" as const, labels: { boxWidth: 10, font: { size: 11 }, color: textColor(), padding: 12 } },
    },
  };
}

export function radarOpts() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    // Point labels at the left/right extremes of the circle get clipped by
    // the canvas edge without generous layout padding — this is what was
    // cutting off the start of longer axis labels (e.g. "GDP per Capita").
    layout: { padding: { top: 16, bottom: 16, left: 46, right: 46 } },
    scales: {
      r: {
        angleLines: { color: gridColor() },
        grid: { color: gridColor() },
        pointLabels: { color: textColor(), font: { size: 12.5, weight: 600 } },
        ticks: { display: false, backdropColor: "transparent" },
      },
    },
    plugins: { legend: { labels: { color: textColor(), boxWidth: 10, font: { size: 12.5 } } } },
  };
}
