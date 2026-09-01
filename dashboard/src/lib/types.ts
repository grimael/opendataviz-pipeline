export interface IndicatorMeta {
  code: string;
  short_name: string;
  name: string;
  unit: string;
}

export type IndicatorsByPole = Record<string, IndicatorMeta[]>;

export interface TrendPoint {
  year: number;
  value: number | null;
  is_imputed: boolean;
}

export interface CountryProfile {
  name: string;
  iso3: string;
  iso2: string;
  region: string;
  income_level: string;
  capital_city: string;
  lat: number;
  lng: number;
  latest: Record<string, number>;
  latest_is_imputed: Record<string, boolean>;
  trends: Record<string, TrendPoint[]>;
}

export type CountryProfiles = Record<string, CountryProfile>;

export interface RankingRow {
  rank: number;
  country: string;
  iso3: string;
  value: number;
  year: number;
}

export type Rankings = Record<string, RankingRow[]>;

export interface IndicatorSummary {
  name: string;
  category: string;
  unit: string;
  avg: number | null;
  min: number | null;
  max: number | null;
  median: number | null;
  countries: number;
}

export interface SummaryStats {
  _africa_totals: {
    total_gdp: number;
    total_population: number;
    countries_tracked: number;
    indicators_tracked: number;
  };
  [shortName: string]: IndicatorSummary | any;
}

export interface ProjectionPoint {
  year: number;
  value: number;
  method: string;
  confidence: number | null;
}

export type Projections = Record<string, Record<string, ProjectionPoint[]>>;

export interface QualityDimensionDetail {
  indicator: string;
  name: string;
  status: "pass" | "warn" | "fail";
  [key: string]: any;
}

export interface QualityReport {
  overall_score: number;
  last_run: string;
  dimensions: {
    completeness: { score: number; details: QualityDimensionDetail[] };
    validity: { score: number; details: QualityDimensionDetail[] };
    freshness: { score: number; details: QualityDimensionDetail[] };
  };
  imputation?: {
    non_null_records: number;
    imputed_records: number;
    observed_records: number;
    imputed_pct: number;
    by_method: Record<string, number>;
  };
  [key: string]: any;
}

export interface DashboardData {
  profiles: CountryProfiles;
  rankings: Rankings;
  summary: SummaryStats;
  quality: QualityReport;
  indicators: IndicatorsByPole;
  projections: Projections;
}

export const POLES = ["Economy", "Health", "Education", "Infrastructure"] as const;
export type Pole = (typeof POLES)[number];

export const POLE_META: Record<Pole, { label: string; sidebarIcon: string; accent: string }> = {
  Economy: { label: "Économie", sidebarIcon: "ic-coin", accent: "economy" },
  Health: { label: "Santé", sidebarIcon: "ic-pulse", accent: "health" },
  Education: { label: "Éducation", sidebarIcon: "ic-cap", accent: "education" },
  Infrastructure: { label: "Infrastructure", sidebarIcon: "ic-tower", accent: "infrastructure" },
};
