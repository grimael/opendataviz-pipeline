import Chart from "chart.js/auto";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { loadDashboardData, buildIndicatorLabelMap } from "./data";
import { formatCurrency, formatLargeNum, formatValue } from "./format";
import { COLORS, textColor, gridColor, barOpts, lineOpts, donutOpts } from "./chartTheme";
import type { DashboardData } from "./types";

declare global {
  interface Window {
    __openCountry?: (iso3: string) => void;
  }
}

let DATA: DashboardData;
let LABELS: Record<string, string> = {};
const CHARTS: Record<string, Chart> = {};
let MAP: L.Map | null = null;
let GEO_LAYER: L.GeoJSON | null = null;

async function main() {
  DATA = await loadDashboardData();
  LABELS = buildIndicatorLabelMap(DATA.indicators);

  renderKPIs();
  renderQualityMini();
  chartGDPBar();
  chartPopRegion();
  chartIncomeLevel();
  chartGrowthLine();
  chartScatter();
  initMapIndicatorSelect();
  initMapObserver();

  window.__openCountry = openCountry;
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("openCountry");
  if (requested && DATA.profiles[requested]) openCountry(requested);
}

function renderKPIs() {
  const totals = DATA.summary._africa_totals || {};
  const avgGrowth = DATA.summary.gdp_growth?.avg || 0;
  const avgLife = DATA.summary.life_expectancy?.avg || 0;
  const avgLiteracy = DATA.summary.literacy_rate?.avg || 0;
  const avgInternet = DATA.summary.internet_users?.avg || 0;
  setText("kpi-gdp", formatCurrency(totals.total_gdp));
  setText("kpi-population", formatLargeNum(totals.total_population));
  setText("kpi-growth", avgGrowth.toFixed(1) + "%");
  setText("kpi-life", avgLife.toFixed(1) + " ans");
  setText("kpi-literacy", avgLiteracy.toFixed(1) + "%");
  setText("kpi-internet", avgInternet.toFixed(1) + "%");
}

function setText(id: string, text: string) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function renderQualityMini() {
  const dims = DATA.quality.dimensions || ({} as any);
  const items = [
    { label: "Complétude", score: dims.completeness?.score },
    { label: "Validité", score: dims.validity?.score },
    { label: "Fraîcheur", score: dims.freshness?.score },
    { label: "Imputé (ML)", score: DATA.quality.imputation?.imputed_pct, suffix: "%" },
  ];
  const el = document.getElementById("quality-mini");
  if (!el) return;
  el.innerHTML = items
    .map(
      (i) => `
    <div class="rounded-2xl bg-surface-2 p-3">
      <div class="font-display text-xl font-extrabold tabular-nums">${i.score != null ? i.score : "—"}${i.suffix || ""}</div>
      <div class="text-[11px] text-muted mt-0.5">${i.label}</div>
    </div>`
    )
    .join("");
}

function chartGDPBar() {
  const ranked = (DATA.rankings.gdp || []).slice(0, 10);
  const ctx = (document.getElementById("chart-gdp-bar") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.gdpBar = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ranked.map((r) => r.country),
      datasets: [
        {
          label: "PIB (Md US$)",
          data: ranked.map((r) => r.value / 1e9),
          backgroundColor: ranked.map((_, i) => COLORS[i % COLORS.length] + "cc"),
          borderRadius: 6,
        },
      ],
    },
    options: { ...barOpts(), onClick: (_: any, els: any) => els[0] && openCountry(ranked[els[0].index].iso3) },
  });
}

// Custom HTML legend instead of Chart.js's built-in one: full control over
// wrapping/truncation means nothing ever gets clipped by the card bounds.
function renderHtmlLegend(containerId: string, labels: string[], colors: string[], formatValue: (i: number) => string) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = labels
    .map(
      (label, i) => `
    <div class="flex items-center gap-2 min-w-0">
      <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${colors[i]}"></span>
      <span class="truncate text-ink">${label}</span>
      <span class="ml-auto pl-2 text-muted font-semibold tabular-nums shrink-0">${formatValue(i)}</span>
    </div>`
    )
    .join("");
}

function chartPopRegion() {
  const regions: Record<string, number> = {};
  Object.values(DATA.profiles).forEach((p) => {
    const r = p.region || "Autre";
    regions[r] = (regions[r] || 0) + (p.latest?.population || 0);
  });
  const labels = Object.keys(regions).sort((a, b) => regions[b] - regions[a]);
  const colors = labels.map((_, i) => COLORS[i % COLORS.length]);
  const total = labels.reduce((sum, l) => sum + regions[l], 0);

  const ctx = (document.getElementById("chart-pop-region") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.popRegion = new Chart(ctx, {
    type: "doughnut",
    data: { labels, datasets: [{ data: labels.map((l) => regions[l]), backgroundColor: colors, borderWidth: 0 }] },
    options: {
      ...donutOpts(),
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c: any) => c.label + ": " + formatLargeNum(c.raw) } } },
    },
  });
  renderHtmlLegend("pop-region-legend", labels, colors, (i) => `${Math.round((regions[labels[i]] / total) * 100)}%`);
}

function chartIncomeLevel() {
  const levels: Record<string, number> = {};
  Object.values(DATA.profiles).forEach((p) => {
    const lvl = p.income_level || "Inconnu";
    levels[lvl] = (levels[lvl] || 0) + 1;
  });
  const labels = Object.keys(levels).sort((a, b) => levels[b] - levels[a]);
  const colors = labels.map((_, i) => COLORS[(i + 4) % COLORS.length]);

  const ctx = (document.getElementById("chart-income-level") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.incomeLevel = new Chart(ctx, {
    type: "pie",
    data: { labels, datasets: [{ data: labels.map((l) => levels[l]), backgroundColor: colors, borderWidth: 0 }] },
    options: {
      ...donutOpts(),
      cutout: 0,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c: any) => `${c.label}: ${c.raw} pays` } } },
    },
  });
  renderHtmlLegend("income-level-legend", labels, colors, (i) => `${levels[labels[i]]}`);
}

function chartGrowthLine() {
  const yearData: Record<string, number[]> = {};
  Object.values(DATA.profiles).forEach((p) => {
    (p.trends?.gdp_growth || []).forEach((t) => {
      if (t.value == null) return;
      (yearData[t.year] ||= []).push(t.value);
    });
  });
  const years = Object.keys(yearData).sort();
  const avgs = years.map((y) => {
    const vals = yearData[y];
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  });
  const ctx = (document.getElementById("chart-growth-line") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.growth = new Chart(ctx, {
    type: "line",
    data: { labels: years, datasets: [{ label: "Croissance PIB moy. (%)", data: avgs, borderColor: COLORS[0], backgroundColor: COLORS[0] + "22", fill: true, tension: 0.35, pointRadius: 2 }] },
    options: lineOpts(),
  });
}

function chartScatter() {
  const points: { x: number; y: number; iso3: string; name: string; pop: number }[] = [];
  Object.entries(DATA.profiles).forEach(([iso3, p]) => {
    const gdp = p.latest?.gdp;
    const pop = p.latest?.population;
    const le = p.latest?.life_expectancy;
    if (gdp && pop && le) points.push({ x: gdp / pop, y: le, iso3, name: p.name, pop });
  });
  const ctx = (document.getElementById("chart-scatter") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.scatter = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Pays",
          data: points.map((p) => ({ x: p.x, y: p.y })),
          backgroundColor: COLORS[6] + "aa",
          pointRadius: points.map((p) => Math.max(3, Math.sqrt(p.pop / 1e6))),
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { bottom: 40, right: 12, top: 8, left: 4 } },
      scales: {
        x: {
          type: "logarithmic",
          title: { display: true, text: "PIB / habitant (US$)", color: textColor(), font: { size: 13, weight: "bold" }, padding: { top: 10 } },
          // A log-scale x-axis generates many ticks (200, 300, 500, 1000...);
          // left to auto-rotate, they and the axis title below them outgrow
          // the card. Horizontal-only + capped count, plus generous bottom
          // layout padding, guarantees the title never sits at the card edge.
          ticks: { color: textColor(), maxRotation: 0, minRotation: 0, autoSkip: true, maxTicksLimit: 6, font: { size: 12.5 } },
          grid: { color: gridColor() },
        },
        y: {
          title: { display: true, text: "Espérance de vie (années)", color: textColor(), font: { size: 13, weight: "bold" } },
          ticks: { color: textColor(), font: { size: 12.5 } },
          grid: { color: gridColor() },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c: any) => { const p = points[c.dataIndex]; return `${p.name}: $${Math.round(p.x).toLocaleString("en-US")}/hab, ${p.y.toFixed(1)} ans`; } } },
      },
      onClick: (_: any, els: any) => els[0] && openCountry(points[els[0].index].iso3),
    } as any,
  });
}

// ── Map (lazy-init on visibility, since it's below the fold) ──
function initMapIndicatorSelect() {
  const sel = document.getElementById("map-indicator") as HTMLSelectElement;
  sel.innerHTML = Object.entries(DATA.indicators)
    .map(([pole, list]) => `<optgroup label="${pole}">${list.map((i) => `<option value="${i.short_name}" ${i.short_name === "gdp" ? "selected" : ""}>${i.name}</option>`).join("")}</optgroup>`)
    .join("");
  sel.addEventListener("change", () => {
    if (GEO_LAYER && MAP) renderChoropleth((GEO_LAYER as any)._geoData, sel.value);
  });
}

function initMapObserver() {
  const el = document.getElementById("map")!;
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !MAP) {
      initMap();
      observer.disconnect();
    }
  });
  observer.observe(el);
}

async function initMap() {
  MAP = L.map("map", { scrollWheelZoom: true, zoomControl: true }).setView([2, 20], 3);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 8,
  }).addTo(MAP);

  const geo = await fetch("https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson").then((r) => r.json());
  const africanIso3 = new Set(Object.keys(DATA.profiles));
  geo.features = geo.features.filter((f: any) => africanIso3.has(f.properties["ISO3166-1-Alpha-3"]));

  renderChoropleth(geo, (document.getElementById("map-indicator") as HTMLSelectElement).value || "gdp");
}

function getColor(value: number, min: number, max: number): string {
  if (max === min) return "#00D4FF";
  const t = (value - min) / (max - min);
  const colors = [
    [244, 247, 252], [0, 212, 255], [0, 119, 190], [26, 58, 92], [10, 22, 40],
  ];
  const idx = Math.min(Math.floor(t * (colors.length - 1)), colors.length - 2);
  const f = t * (colors.length - 1) - idx;
  const [r, g, b] = colors[idx].map((c, i) => Math.round(c + f * (colors[idx + 1][i] - c)));
  return `rgb(${r},${g},${b})`;
}

function renderChoropleth(geo: any, indicator: string) {
  if (!MAP) return;
  if (GEO_LAYER) MAP.removeLayer(GEO_LAYER);

  const values: Record<string, number | null> = {};
  Object.entries(DATA.profiles).forEach(([iso3, p]) => { values[iso3] = p.latest?.[indicator] ?? null; });
  const nums = Object.values(values).filter((v): v is number => v !== null);
  const min = Math.min(...nums);
  const max = Math.max(...nums);

  GEO_LAYER = L.geoJSON(geo, {
    style: (feature: any) => {
      const iso3 = feature.properties["ISO3166-1-Alpha-3"];
      const val = values[iso3];
      return { fillColor: val != null ? getColor(val, min, max) : "#ccc", weight: 1, color: "#fff", fillOpacity: 0.82 };
    },
    onEachFeature: (feature: any, layer: any) => {
      const iso3 = feature.properties["ISO3166-1-Alpha-3"];
      const profile = DATA.profiles[iso3];
      if (profile) {
        const val = profile.latest?.[indicator];
        layer.bindPopup(`<strong>${profile.name}</strong><br>${LABELS[indicator] || indicator}: ${val != null ? formatValue(val, indicator) : "N/A"}`);
        layer.on("click", () => openCountry(iso3));
      }
    },
  }).addTo(MAP);
  (GEO_LAYER as any)._geoData = geo;
}

// ── Country modal ────────────────────────────────────────
function openCountry(iso3: string) {
  const p = DATA.profiles[iso3];
  if (!p) return;
  setText("modal-title", p.name);
  const meta = document.getElementById("modal-meta")!;
  meta.innerHTML = `${p.region} · ${p.income_level} · Capitale : ${p.capital_city || "—"}`;

  const indicators = ["gdp", "gdp_growth", "population", "inflation", "life_expectancy", "literacy_rate", "internet_users", "electricity_access"];
  const grid = document.getElementById("modal-indicators")!;
  grid.innerHTML = indicators
    .map((ind) => {
      const val = p.latest?.[ind];
      const imputed = p.latest_is_imputed?.[ind];
      return `<div class="rounded-xl bg-surface-2 p-3">
        <div class="font-bold">${val != null ? formatValue(val, ind) : "N/A"}${imputed ? ' <span class="inline-block w-1.5 h-1.5 rounded-full bg-gold align-middle mb-0.5" title="Valeur imputée par ML"></span>' : ""}</div>
        <div class="text-xs text-muted">${LABELS[ind] || ind}</div>
      </div>`;
    })
    .join("");

  CHARTS.modalTrend?.destroy();
  const trend = p.trends?.gdp || [];
  const ctx = (document.getElementById("chart-modal-trend") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.modalTrend = new Chart(ctx, {
    type: "line",
    data: { labels: trend.map((t) => t.year), datasets: [{ label: "PIB (Md US$)", data: trend.map((t) => (t.value || 0) / 1e9), borderColor: COLORS[0], backgroundColor: COLORS[0] + "22", fill: true, tension: 0.3, pointRadius: 2 }] },
    options: lineOpts(),
  });

  const modal = document.getElementById("country-modal")!;
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

document.getElementById("modal-close")?.addEventListener("click", closeModal);
document.getElementById("country-modal")?.addEventListener("click", (e) => { if (e.target === e.currentTarget) closeModal(); });
function closeModal() {
  const modal = document.getElementById("country-modal")!;
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

main();
