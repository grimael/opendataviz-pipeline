import type { DashboardData, IndicatorMeta, IndicatorsByPole } from "./types";

let cached: DashboardData | null = null;

export async function loadDashboardData(): Promise<DashboardData> {
  if (cached) return cached;
  const [profiles, rankings, summary, quality, indicators, projections] = await Promise.all([
    fetch("/data/country_profiles.json").then((r) => r.json()),
    fetch("/data/rankings.json").then((r) => r.json()),
    fetch("/data/summary_stats.json").then((r) => r.json()),
    fetch("/data/quality_report.json").then((r) => r.json()),
    fetch("/data/indicators.json").then((r) => r.json()),
    fetch("/data/projections.json").then((r) => r.json()),
  ]);
  cached = { profiles, rankings, summary, quality, indicators, projections };
  return cached;
}

export function allIndicatorsFlat(byPole: IndicatorsByPole): IndicatorMeta[] {
  return Object.values(byPole).flat();
}

export function buildIndicatorLabelMap(byPole: IndicatorsByPole): Record<string, string> {
  const map: Record<string, string> = {};
  for (const i of allIndicatorsFlat(byPole)) map[i.short_name] = i.name;
  return map;
}
