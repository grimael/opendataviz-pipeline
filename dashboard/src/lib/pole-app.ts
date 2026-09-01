import Chart from "chart.js/auto";
import { loadDashboardData } from "./data";
import { formatValue } from "./format";
import { COLORS, POLE_COLORS, textColor, gridColor, donutOpts, radarOpts } from "./chartTheme";
import type { DashboardData, IndicatorMeta } from "./types";

const RADAR_MAX_AXES = 8;
const MAX_COUNTRIES = 6;

declare global {
  interface Window {
    __POLE_KEY__: string;
  }
}

let DATA: DashboardData;
const POLE_KEY = window.__POLE_KEY__;
const CHARTS: Record<string, Chart> = {};
let selectedCountries: string[] = [];
let kpiPicks: IndicatorMeta[] = [];

function poleIndicators() {
  return DATA.indicators[POLE_KEY] || [];
}

async function main() {
  DATA = await loadDashboardData();
  kpiPicks = poleIndicators().slice(0, 6);

  initCountryPicker();
  initFilters();
  render();
}

// KPIs always reflect the current selection: the Africa-wide average from
// summary_stats.json when nothing is picked, otherwise the average across
// exactly the countries picked (one or several) — never a mix of the two.
function renderKPIs() {
  kpiPicks.forEach((ind, i) => {
    const valueEl = document.getElementById(`kpi-${i}`);
    let value: number | null = null;

    if (selectedCountries.length === 0) {
      value = (DATA.summary as any)[ind.short_name]?.avg ?? null;
    } else {
      const values = selectedCountries
        .map((iso3) => DATA.profiles[iso3]?.latest?.[ind.short_name])
        .filter((v): v is number => v != null);
      value = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
    }

    if (valueEl) valueEl.textContent = value != null ? formatValue(value, ind.short_name) : "—";
  });
}

const COUNTRY_CHIP_COLORS = ["#E3F8FF", "#FFE9DF", "#DCFCED", "#E2EBF3", "#FFF3DC", "#FFE1E7"];
const COUNTRY_CHIP_TEXT = ["#0077BE", "#E85A2A", "#00A85C", "#1A3A5C", "#B87800", "#D6123A"];

function initCountryPicker() {
  // Nothing preselected: the trend chart opens on the continent-wide average,
  // and only shows individual country lines once the user actually picks some.
  selectedCountries = [];
  renderCountryChips();

  const input = document.getElementById("country-picker-input") as HTMLInputElement;
  const results = document.getElementById("country-picker-results")!;

  function showMatches() {
    const q = input.value.trim().toLowerCase();
    const available = Object.entries(DATA.profiles).filter(([iso3]) => !selectedCountries.includes(iso3));
    const matches = (q ? available.filter(([, p]) => p.name.toLowerCase().includes(q)) : available).sort((a, b) =>
      a[1].name.localeCompare(b[1].name)
    );

    if (selectedCountries.length >= MAX_COUNTRIES) {
      results.innerHTML = `<div class="px-3.5 py-2.5 text-xs text-muted">Maximum ${MAX_COUNTRIES} pays — retirez-en un pour en ajouter un autre</div>`;
      results.classList.remove("hidden");
      return;
    }
    if (!matches.length) {
      results.classList.add("hidden");
      return;
    }
    results.innerHTML = matches
      .map(([iso3, p]) => `<button type="button" data-iso3="${iso3}" class="w-full text-left px-3.5 py-2.5 text-sm hover:bg-surface-2 transition-colors">${p.name}</button>`)
      .join("");
    results.classList.remove("hidden");
  }

  input.addEventListener("focus", showMatches);
  input.addEventListener("input", showMatches);
  document.addEventListener("click", (e) => {
    if (!(e.target instanceof Node)) return;
    if (!results.contains(e.target) && e.target !== input) results.classList.add("hidden");
  });
  results.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-iso3]");
    if (!btn || selectedCountries.length >= MAX_COUNTRIES) return;
    selectedCountries.push(btn.dataset.iso3!);
    input.value = "";
    results.classList.add("hidden");
    renderCountryChips();
    render();
  });
}

function renderCountryChips() {
  const box = document.getElementById("country-chip-box")!;
  const input = document.getElementById("country-picker-input")!;
  box.querySelectorAll("[data-chip]").forEach((el) => el.remove());
  selectedCountries.forEach((iso3, i) => {
    const chip = document.createElement("span");
    chip.dataset.chip = iso3;
    chip.className = "inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-lg text-xs font-bold";
    chip.style.background = COUNTRY_CHIP_COLORS[i % COUNTRY_CHIP_COLORS.length];
    chip.style.color = COUNTRY_CHIP_TEXT[i % COUNTRY_CHIP_TEXT.length];
    chip.innerHTML = `${DATA.profiles[iso3]?.name || iso3} <svg width="12" height="12" class="cursor-pointer" data-remove="${iso3}"><use href="#ic-close"/></svg>`;
    box.insertBefore(chip, input);
  });
  box.querySelectorAll<SVGElement>("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedCountries = selectedCountries.filter((c) => c !== btn.dataset.remove);
      renderCountryChips();
      render();
    });
  });
}

function initFilters() {
  document.getElementById("pole-indicator")?.addEventListener("change", render);
  ["toggle-imputed", "toggle-projected", "pole-year-from", "pole-year-to"].forEach((id) =>
    document.getElementById(id)?.addEventListener("change", render)
  );
}

function currentSelection() {
  return {
    shortName: (document.getElementById("pole-indicator") as HTMLSelectElement).value,
    countries: selectedCountries.slice(0, MAX_COUNTRIES),
    yearFrom: parseInt((document.getElementById("pole-year-from") as HTMLInputElement).value, 10) || 2000,
    yearTo: parseInt((document.getElementById("pole-year-to") as HTMLInputElement).value, 10) || 2029,
    showImputed: (document.getElementById("toggle-imputed") as HTMLInputElement).checked,
    showProjected: (document.getElementById("toggle-projected") as HTMLInputElement).checked,
  };
}

function render() {
  const sel = currentSelection();
  renderKPIs();
  renderTrendChart(sel);
  renderRadarChart(sel.shortName);
  renderRegionDonut(sel.shortName);
  renderRankings(sel.shortName);
}

// Year -> average value across every country that has a real (or, if
// includeImputed, imputed) reading for that year — used for the "Moyenne
// Afrique" line when no country is selected.
function africaAverageSeries(shortName: string, yearFrom: number, yearTo: number, includeImputed: boolean) {
  const byYear: Record<number, number[]> = {};
  Object.values(DATA.profiles).forEach((p) => {
    (p.trends?.[shortName] || []).forEach((t) => {
      if (t.value == null || t.year < yearFrom || t.year > yearTo) return;
      if (t.is_imputed && !includeImputed) return;
      (byYear[t.year] ||= []).push(t.value);
    });
  });
  return Object.keys(byYear)
    .map(Number)
    .sort((a, b) => a - b)
    .map((year) => ({ year, value: byYear[year].reduce((a, b) => a + b, 0) / byYear[year].length }));
}

function africaAverageProjection(shortName: string, yearTo: number) {
  const byYear: Record<number, number[]> = {};
  Object.values(DATA.projections).forEach((byIndicator) => {
    (byIndicator[shortName] || []).forEach((p) => {
      if (p.year > yearTo) return;
      (byYear[p.year] ||= []).push(p.value);
    });
  });
  return Object.keys(byYear)
    .map(Number)
    .sort((a, b) => a - b)
    .map((year) => ({ year, value: byYear[year].reduce((a, b) => a + b, 0) / byYear[year].length }));
}

function renderTrendChart(sel: ReturnType<typeof currentSelection>) {
  const indMeta = poleIndicators().find((i) => i.short_name === sel.shortName);
  const titleEl = document.getElementById("trend-chart-title");
  if (titleEl) titleEl.textContent = indMeta?.name || "";

  const datasets: any[] = [];

  if (sel.countries.length === 0) {
    const color = COLORS[0];
    const series = africaAverageSeries(sel.shortName, sel.yearFrom, sel.yearTo, sel.showImputed);
    datasets.push({
      label: "Moyenne Afrique",
      data: series.map((t) => ({ x: t.year, y: t.value })),
      borderColor: color,
      backgroundColor: color + "22",
      pointRadius: 2.5,
      tension: 0.3,
      fill: true,
    });
    if (sel.showProjected && series.length) {
      const proj = africaAverageProjection(sel.shortName, sel.yearTo);
      if (proj.length) {
        const lastReal = series[series.length - 1];
        datasets.push({
          label: "Moyenne Afrique (projeté)",
          data: [{ x: lastReal.year, y: lastReal.value }, ...proj.map((p) => ({ x: p.year, y: p.value }))],
          borderColor: color,
          borderDash: [6, 4],
          pointRadius: 2,
          backgroundColor: "transparent",
          tension: 0.3,
          fill: false,
        });
      }
    }
  }

  sel.countries.forEach((iso3, i) => {
    const color = COLORS[i % COLORS.length];
    const name = DATA.profiles[iso3]?.name || iso3;
    let trend = (DATA.profiles[iso3]?.trends?.[sel.shortName] || []).filter((t) => t.year >= sel.yearFrom && t.year <= sel.yearTo);
    if (!sel.showImputed) trend = trend.filter((t) => !t.is_imputed);

    datasets.push({
      label: name,
      data: trend.map((t) => ({ x: t.year, y: t.value })),
      borderColor: color,
      backgroundColor: color + "22",
      pointBackgroundColor: trend.map((t) => (t.is_imputed ? color + "55" : color)),
      pointRadius: trend.map((t) => (t.is_imputed ? 4 : 2.5)),
      tension: 0.3,
      fill: false,
    });

    if (sel.showProjected && trend.length) {
      const proj = (DATA.projections[iso3]?.[sel.shortName] || []).filter((p) => p.year <= sel.yearTo);
      if (proj.length) {
        const lastReal = trend[trend.length - 1];
        datasets.push({
          label: `${name} (projeté)`,
          data: [{ x: lastReal.year, y: lastReal.value }, ...proj.map((p) => ({ x: p.year, y: p.value }))],
          borderColor: color,
          borderDash: [6, 4],
          pointRadius: 2,
          backgroundColor: "transparent",
          tension: 0.3,
          fill: false,
        });
      }
    }
  });

  CHARTS.trend?.destroy();
  const ctx = (document.getElementById("chart-trend") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.trend = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Année", color: textColor() },
          ticks: { color: textColor(), maxRotation: 0, minRotation: 0, autoSkip: true, maxTicksLimit: 10 },
          grid: { color: gridColor() },
        },
        y: { ticks: { color: textColor() }, grid: { color: gridColor() } },
      },
      plugins: { legend: { labels: { color: textColor(), boxWidth: 14, font: { size: 12, weight: "bold" }, filter: (item: any) => !item.text.includes("(projeté)") } } },
    } as any,
  });
}

function normalizedScores(shortName: string, isos: string[]): Record<string, number> {
  const vals = isos.map((iso3) => DATA.profiles[iso3]?.latest?.[shortName]).filter((v): v is number => v != null);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const out: Record<string, number> = {};
  isos.forEach((iso3) => {
    const v = DATA.profiles[iso3]?.latest?.[shortName];
    out[iso3] = v != null && max > min ? ((v - min) / (max - min)) * 100 : 0;
  });
  return out;
}

// Wraps a long indicator name onto up to 2 lines (Chart.js pointLabels
// accepts an array of strings per label) instead of truncating with an
// ellipsis — the radar card now has enough room for this to stay legible.
function wrapRadarLabel(name: string, maxLineLen = 15): string | string[] {
  if (name.length <= maxLineLen) return name;
  const words = name.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxLineLen && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  if (lines.length <= 2) return lines;
  return [lines[0], lines.slice(1).join(" ").length > maxLineLen ? lines[1].slice(0, maxLineLen - 1) + "…" : lines.slice(1).join(" ")];
}

function renderRadarChart(selectedShort: string) {
  // Selected indicator first (so it's always represented), then fill up to
  // RADAR_MAX_AXES with the rest of the pole — 15 axes on one radar is
  // unreadable, so we cap it rather than showing every indicator at once.
  const all = poleIndicators();
  const selected = all.find((i) => i.short_name === selectedShort);
  const rest = all.filter((i) => i.short_name !== selectedShort);
  const indicators = [selected, ...rest].filter((i): i is NonNullable<typeof i> => !!i).slice(0, RADAR_MAX_AXES);

  const topIsos = (DATA.rankings[selectedShort] || []).slice(0, 5).map((r) => r.iso3);
  if (!topIsos.length) return;

  const perIndicatorScores = indicators.map((ind) => normalizedScores(ind.short_name, topIsos));

  const datasets = topIsos.map((iso3, i) => ({
    label: DATA.profiles[iso3]?.name || iso3,
    data: perIndicatorScores.map((scores) => scores[iso3] ?? 0),
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length] + "22",
    pointRadius: 1.5,
  }));

  CHARTS.radar?.destroy();
  const ctx = (document.getElementById("chart-radar") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.radar = new Chart(ctx, {
    type: "radar",
    data: { labels: indicators.map((i) => wrapRadarLabel(i.name)), datasets },
    options: { ...radarOpts(), plugins: { legend: { display: false } } } as any,
  });

  const legendEl = document.getElementById("radar-legend");
  if (legendEl) {
    legendEl.innerHTML = topIsos
      .map(
        (iso3, i) => `<span class="inline-flex items-center gap-1.5">
        <span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background:${COLORS[i % COLORS.length]}"></span>
        ${DATA.profiles[iso3]?.name || iso3}
      </span>`
      )
      .join("");
  }
}

function renderRegionDonut(shortName: string) {
  const sums: Record<string, number> = {};
  const counts: Record<string, number> = {};
  Object.values(DATA.profiles).forEach((p) => {
    const v = p.latest?.[shortName];
    if (v == null) return;
    const r = p.region || "Autre";
    sums[r] = (sums[r] || 0) + v;
    counts[r] = (counts[r] || 0) + 1;
  });
  const labels = Object.keys(sums).sort((a, b) => sums[b] / counts[b] - sums[a] / counts[a]);
  const avgs = labels.map((r) => Math.round((sums[r] / counts[r]) * 10) / 10);
  const accent = POLE_COLORS[POLE_KEY] || COLORS[0];
  const colors = labels.map((_, i) => shade(accent, i));

  CHARTS.donut?.destroy();
  const ctx = (document.getElementById("chart-region-donut") as HTMLCanvasElement).getContext("2d")!;
  CHARTS.donut = new Chart(ctx, {
    type: "doughnut",
    data: { labels, datasets: [{ data: avgs, backgroundColor: colors, borderWidth: 0 }] },
    options: { ...donutOpts(), plugins: { legend: { display: false } } } as any,
  });

  const legendEl = document.getElementById("region-donut-legend");
  if (legendEl) {
    legendEl.innerHTML = labels
      .map(
        (label, i) => `<div class="flex items-center gap-2 min-w-0">
        <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${colors[i]}"></span>
        <span class="truncate text-ink">${label}</span>
        <span class="ml-auto pl-2 text-muted font-semibold tabular-nums shrink-0">${avgs[i]}</span>
      </div>`
      )
      .join("");
  }
}

function shade(hex: string, i: number): string {
  const alphas = ["ff", "cc", "aa", "88", "66", "44"];
  return hex + (alphas[i] || "44");
}

function renderRankings(shortName: string) {
  const ranked = DATA.rankings[shortName] || [];
  const body = document.getElementById("rankings-body")!;
  body.innerHTML = ranked
    .map(
      (r) => `<tr class="border-b border-border last:border-0">
      <td class="py-2 pr-3 font-mono text-muted">${r.rank}</td>
      <td class="py-2 pr-3 font-medium">${r.country}</td>
      <td class="py-2 pr-3 text-right font-mono">${formatValue(r.value, shortName)}</td>
      <td class="py-2 text-right text-muted">${r.year}</td>
    </tr>`
    )
    .join("");
}

main();
