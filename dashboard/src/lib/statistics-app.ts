import Chart from "chart.js/auto";
import { BoxPlotController, BoxAndWiskers, ViolinController, Violin } from "@sgratzl/chartjs-chart-boxplot";
import { loadDashboardData } from "./data";
import { formatValue } from "./format";
import { COLORS, textColor, gridColor } from "./chartTheme";
import { summarize, linearRegression, histogram, sturgesBinCount, correlationMatrix } from "./stats";
import type { DashboardData, IndicatorMeta, IndicatorsByPole } from "./types";

Chart.register(BoxPlotController, BoxAndWiskers, ViolinController, Violin);

declare global {
  interface Window {
    __INDICATORS_BY_POLE__: IndicatorsByPole;
  }
}

const INDICATORS_BY_POLE = window.__INDICATORS_BY_POLE__;
const ALL_INDICATORS: IndicatorMeta[] = Object.values(INDICATORS_BY_POLE).flat();
const POLE_LABELS: Record<string, string> = { Economy: "Économie", Health: "Santé", Education: "Éducation", Infrastructure: "Infrastructure" };

function indByShort(short: string): IndicatorMeta | undefined {
  return ALL_INDICATORS.find((i) => i.short_name === short);
}

let DATA: DashboardData;
let currentChart: Chart | null = null;
let currentCanvas: HTMLCanvasElement | null = null;

type AnalysisType = "distribution" | "comparison" | "correlation" | "evolution" | "ranking";
type ChartTypeId = "histogram" | "boxplot" | "violin" | "scatter" | "bubble" | "heatmap" | "line" | "bar";

const CHART_OPTIONS: Record<AnalysisType, { id: ChartTypeId; label: string }[]> = {
  distribution: [
    { id: "histogram", label: "Histogramme" },
    { id: "boxplot", label: "Boîte à moustaches" },
    { id: "violin", label: "Violon" },
  ],
  comparison: [
    { id: "scatter", label: "Nuage de points" },
    { id: "bubble", label: "Bulles" },
  ],
  correlation: [{ id: "heatmap", label: "Matrice de corrélation" }],
  evolution: [{ id: "line", label: "Courbes" }],
  ranking: [{ id: "bar", label: "Barres" }],
};

const state = {
  analysis: "distribution" as AnalysisType,
  chartType: "histogram" as ChartTypeId,
  indicatorX: "gdp",
  indicatorY: "life_expectancy",
  indicatorsMulti: ["gdp", "life_expectancy", "literacy_rate", "internet_users"] as string[],
  countries: [] as string[],
  region: "",
  incomeLevel: "",
  year: 2024,
  yearFrom: 2000,
  yearTo: 2024,
  includeImputed: true,
  rankTopN: 15,
  rankOrder: "desc" as "desc" | "asc",
};

const CHIP_BG = ["#E3F8FF", "#FFE9DF", "#DCFCED", "#E2EBF3", "#FFF3DC", "#FFE1E7", "#DFEEFF", "#FFE9DF"];
const CHIP_TEXT = ["#0077BE", "#E85A2A", "#00A85C", "#1A3A5C", "#B87800", "#D6123A", "#0A1628", "#FF6B35"];

async function main() {
  DATA = await loadDashboardData();
  document.querySelectorAll<HTMLButtonElement>("#analysis-type-picker [data-analysis]").forEach((btn) => {
    btn.addEventListener("click", () => selectAnalysis(btn.dataset.analysis as AnalysisType));
  });
  document.getElementById("btn-export-png")?.addEventListener("click", exportCurrentPNG);
  selectAnalysis("distribution");
}

function selectAnalysis(a: AnalysisType) {
  state.analysis = a;
  paintAnalysisPicker();
  renderIndicatorControls();
  renderFilterControls();
  renderChartTypePicker();
  renderChartOnly();
}

function paintAnalysisPicker() {
  document.querySelectorAll<HTMLButtonElement>("#analysis-type-picker [data-analysis]").forEach((btn) => {
    btn.dataset.active = String(btn.dataset.analysis === state.analysis);
  });
}

// ── Indicator / country pickers ──────────────────────────────

function indicatorSelectHtml(id: string, selected: string): string {
  const groups = Object.entries(INDICATORS_BY_POLE)
    .map(
      ([pole, list]) =>
        `<optgroup label="${POLE_LABELS[pole] || pole}">${list
          .map((i) => `<option value="${i.short_name}" ${i.short_name === selected ? "selected" : ""}>${i.name}</option>`)
          .join("")}</optgroup>`
    )
    .join("");
  return `<select id="${id}" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 w-full">${groups}</select>`;
}

function renderIndicatorControls() {
  const el = document.getElementById("indicator-controls")!;

  if (state.analysis === "distribution" || state.analysis === "ranking") {
    el.innerHTML = `
      <div class="flex flex-col gap-1.5">
        <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Indicateur</label>
        ${indicatorSelectHtml("stat-indicator-x", state.indicatorX)}
      </div>`;
    bindIndicatorSelect("stat-indicator-x", (v) => (state.indicatorX = v));
  } else if (state.analysis === "comparison") {
    el.innerHTML = `
      <div class="flex flex-col gap-1.5">
        <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Axe X</label>
        ${indicatorSelectHtml("stat-indicator-x", state.indicatorX)}
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Axe Y</label>
        ${indicatorSelectHtml("stat-indicator-y", state.indicatorY)}
      </div>`;
    bindIndicatorSelect("stat-indicator-x", (v) => (state.indicatorX = v));
    bindIndicatorSelect("stat-indicator-y", (v) => (state.indicatorY = v));
  } else if (state.analysis === "correlation") {
    el.innerHTML = `
      <div class="flex flex-col gap-1.5 relative">
        <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Indicateurs (3 à 8)</label>
        <div id="chip-box-corr" class="flex flex-wrap items-center gap-1.5 bg-surface-2 border border-border rounded-xl px-2 py-1.5 min-h-[42px]">
          <input id="chip-input-corr" type="text" placeholder="Ajouter un indicateur…" autocomplete="off" class="flex-1 min-w-[100px] bg-transparent outline-none text-[13px] px-1.5 py-1 text-ink placeholder:text-muted" />
        </div>
        <div id="chip-results-corr" class="hidden absolute left-0 top-full mt-1.5 w-full bg-surface border border-border rounded-xl shadow-lg overflow-hidden z-30 max-h-72 overflow-y-auto"></div>
      </div>`;
    setupChipPicker({
      inputId: "chip-input-corr",
      resultsId: "chip-results-corr",
      chipBoxId: "chip-box-corr",
      items: ALL_INDICATORS.map((i) => ({ id: i.short_name, label: i.name })),
      selected: state.indicatorsMulti,
      max: 8,
      onChange: renderChartOnly,
    });
  } else if (state.analysis === "evolution") {
    el.innerHTML = `
      <div class="flex flex-col gap-1.5">
        <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Indicateur</label>
        ${indicatorSelectHtml("stat-indicator-x", state.indicatorX)}
      </div>
      <div class="flex flex-col gap-1.5 relative">
        <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Pays (optionnel — vide = moyenne Afrique)</label>
        <div id="chip-box-evo" class="flex flex-wrap items-center gap-1.5 bg-surface-2 border border-border rounded-xl px-2 py-1.5 min-h-[42px]">
          <input id="chip-input-evo" type="text" placeholder="Ajouter un pays…" autocomplete="off" class="flex-1 min-w-[100px] bg-transparent outline-none text-[13px] px-1.5 py-1 text-ink placeholder:text-muted" />
        </div>
        <div id="chip-results-evo" class="hidden absolute left-0 top-full mt-1.5 w-full bg-surface border border-border rounded-xl shadow-lg overflow-hidden z-30 max-h-72 overflow-y-auto"></div>
      </div>`;
    bindIndicatorSelect("stat-indicator-x", (v) => (state.indicatorX = v));
    setupChipPicker({
      inputId: "chip-input-evo",
      resultsId: "chip-results-evo",
      chipBoxId: "chip-box-evo",
      items: Object.entries(DATA.profiles).map(([iso3, p]) => ({ id: iso3, label: p.name })),
      selected: state.countries,
      max: 6,
      onChange: renderChartOnly,
    });
  }
}

function bindIndicatorSelect(id: string, setter: (v: string) => void) {
  document.getElementById(id)?.addEventListener("change", (e) => {
    setter((e.target as HTMLSelectElement).value);
    renderChartOnly();
  });
}

function setupChipPicker(opts: {
  inputId: string;
  resultsId: string;
  chipBoxId: string;
  items: { id: string; label: string }[];
  selected: string[];
  max: number;
  onChange: () => void;
}) {
  const input = document.getElementById(opts.inputId) as HTMLInputElement;
  const results = document.getElementById(opts.resultsId)!;
  const chipBox = document.getElementById(opts.chipBoxId)!;

  function renderChips() {
    chipBox.querySelectorAll("[data-chip]").forEach((el) => el.remove());
    opts.selected.forEach((id, i) => {
      const item = opts.items.find((it) => it.id === id);
      const chip = document.createElement("span");
      chip.dataset.chip = id;
      chip.className = "inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-lg text-xs font-bold";
      chip.style.background = CHIP_BG[i % CHIP_BG.length];
      chip.style.color = CHIP_TEXT[i % CHIP_TEXT.length];
      chip.innerHTML = `${item?.label || id} <svg width="12" height="12" class="cursor-pointer" data-remove="${id}"><use href="#ic-close"/></svg>`;
      chipBox.insertBefore(chip, input);
    });
    chipBox.querySelectorAll<SVGElement>("[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = opts.selected.indexOf(btn.dataset.remove!);
        if (idx >= 0) opts.selected.splice(idx, 1);
        renderChips();
        opts.onChange();
      });
    });
  }

  function showMatches() {
    const q = input.value.trim().toLowerCase();
    const available = opts.items.filter((it) => !opts.selected.includes(it.id));
    if (opts.selected.length >= opts.max) {
      results.innerHTML = `<div class="px-3.5 py-2.5 text-xs text-muted">Maximum ${opts.max} — retirez-en un pour en ajouter un autre</div>`;
      results.classList.remove("hidden");
      return;
    }
    const matches = (q ? available.filter((it) => it.label.toLowerCase().includes(q)) : available).slice(0, 60);
    if (!matches.length) {
      results.classList.add("hidden");
      return;
    }
    results.innerHTML = matches
      .map((it) => `<button type="button" data-id="${it.id}" class="w-full text-left px-3.5 py-2.5 text-sm hover:bg-surface-2 transition-colors">${it.label}</button>`)
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
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-id]");
    if (!btn || opts.selected.length >= opts.max) return;
    opts.selected.push(btn.dataset.id!);
    input.value = "";
    results.classList.add("hidden");
    renderChips();
    opts.onChange();
  });

  renderChips();
}

// ── Filters ───────────────────────────────────────────────────

function regionOptions(): string[] {
  const set = new Set<string>();
  Object.values(DATA.profiles).forEach((p) => p.region && set.add(p.region));
  return [...set].sort();
}
function incomeOptions(): string[] {
  const set = new Set<string>();
  Object.values(DATA.profiles).forEach((p) => p.income_level && set.add(p.income_level));
  return [...set].sort();
}
function yearOptions(): number[] {
  const years: number[] = [];
  for (let y = 2024; y >= 2000; y--) years.push(y);
  return years;
}

function renderFilterControls() {
  const el = document.getElementById("filter-controls")!;
  const isEvolution = state.analysis === "evolution";
  const isRanking = state.analysis === "ranking";

  el.innerHTML = `
    ${
      !isEvolution
        ? `
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Région</label>
      <select id="flt-region" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 min-w-[170px]">
        <option value="">Toutes les régions</option>
        ${regionOptions()
          .map((r) => `<option value="${r}" ${state.region === r ? "selected" : ""}>${r}</option>`)
          .join("")}
      </select>
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Niveau de revenu</label>
      <select id="flt-income" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 min-w-[170px]">
        <option value="">Tous niveaux</option>
        ${incomeOptions()
          .map((r) => `<option value="${r}" ${state.incomeLevel === r ? "selected" : ""}>${r}</option>`)
          .join("")}
      </select>
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Année</label>
      <select id="flt-year" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 w-[110px]">
        ${yearOptions()
          .map((y) => `<option value="${y}" ${state.year === y ? "selected" : ""}>${y}</option>`)
          .join("")}
      </select>
    </div>`
        : `
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">De</label>
      <select id="flt-year-from" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 w-[110px]">
        ${yearOptions()
          .map((y) => `<option value="${y}" ${state.yearFrom === y ? "selected" : ""}>${y}</option>`)
          .join("")}
      </select>
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">À</label>
      <select id="flt-year-to" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 w-[110px]">
        ${yearOptions()
          .map((y) => `<option value="${y}" ${state.yearTo === y ? "selected" : ""}>${y}</option>`)
          .join("")}
      </select>
    </div>`
    }
    ${
      isRanking
        ? `
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Nombre de pays</label>
      <select id="flt-topn" class="text-sm font-semibold rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 w-[150px]">
        ${[10, 15, 20, 54]
          .map((n) => `<option value="${n}" ${state.rankTopN === n ? "selected" : ""}>Top ${n === 54 ? "54 (tous)" : n}</option>`)
          .join("")}
      </select>
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-[11px] font-bold text-muted uppercase tracking-wide">Ordre</label>
      <div class="flex items-center gap-1 bg-surface-2 border border-border rounded-xl p-1 h-[42px]">
        <button type="button" data-order="desc" class="rank-order-btn px-3 py-1.5 rounded-lg text-xs font-bold transition-colors">Plus élevé</button>
        <button type="button" data-order="asc" class="rank-order-btn px-3 py-1.5 rounded-lg text-xs font-bold transition-colors">Plus faible</button>
      </div>
    </div>`
        : ""
    }
    <label class="flex items-center gap-2 text-xs font-semibold text-ink cursor-pointer h-[42px]">
      <input type="checkbox" id="flt-imputed" ${state.includeImputed ? "checked" : ""} class="w-4 h-4 rounded accent-brand" />
      Inclure les valeurs imputées (ML)
    </label>
  `;

  document.getElementById("flt-region")?.addEventListener("change", (e) => {
    state.region = (e.target as HTMLSelectElement).value;
    renderChartOnly();
  });
  document.getElementById("flt-income")?.addEventListener("change", (e) => {
    state.incomeLevel = (e.target as HTMLSelectElement).value;
    renderChartOnly();
  });
  document.getElementById("flt-year")?.addEventListener("change", (e) => {
    state.year = Number((e.target as HTMLSelectElement).value);
    renderChartOnly();
  });
  document.getElementById("flt-year-from")?.addEventListener("change", (e) => {
    state.yearFrom = Number((e.target as HTMLSelectElement).value) || 2000;
    renderChartOnly();
  });
  document.getElementById("flt-year-to")?.addEventListener("change", (e) => {
    state.yearTo = Number((e.target as HTMLSelectElement).value) || 2024;
    renderChartOnly();
  });
  document.getElementById("flt-imputed")?.addEventListener("change", (e) => {
    state.includeImputed = (e.target as HTMLInputElement).checked;
    renderChartOnly();
  });
  document.getElementById("flt-topn")?.addEventListener("change", (e) => {
    state.rankTopN = Number((e.target as HTMLSelectElement).value);
    renderChartOnly();
  });
  document.querySelectorAll<HTMLButtonElement>(".rank-order-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.rankOrder = btn.dataset.order as "desc" | "asc";
      paintRankOrderButtons();
      renderChartOnly();
    });
  });
  paintRankOrderButtons();
}

function paintRankOrderButtons() {
  document.querySelectorAll<HTMLButtonElement>(".rank-order-btn").forEach((btn) => {
    const active = btn.dataset.order === state.rankOrder;
    btn.classList.toggle("bg-brand", active);
    btn.classList.toggle("text-white", active);
    btn.classList.toggle("text-muted", !active);
  });
}

// ── Chart-type picker ─────────────────────────────────────────

function renderChartTypePicker() {
  const el = document.getElementById("chart-type-picker")!;
  const options = CHART_OPTIONS[state.analysis];
  if (!options.find((o) => o.id === state.chartType)) state.chartType = options[0].id;
  el.innerHTML = options
    .map((o) => `<button type="button" data-chart-type="${o.id}" class="chart-type-btn px-3.5 py-2 rounded-full border border-border text-xs font-bold transition-colors">${o.label}</button>`)
    .join("");
  el.querySelectorAll<HTMLButtonElement>("[data-chart-type]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.chartType = btn.dataset.chartType as ChartTypeId;
      paintChartTypePicker();
      renderChartOnly();
    });
  });
  paintChartTypePicker();
}

function paintChartTypePicker() {
  document.querySelectorAll<HTMLButtonElement>("#chart-type-picker [data-chart-type]").forEach((btn) => {
    const active = btn.dataset.chartType === state.chartType;
    btn.classList.toggle("bg-brand", active);
    btn.classList.toggle("text-white", active);
    btn.classList.toggle("border-brand", active);
    btn.classList.toggle("text-muted", !active);
  });
}

// ── Data extraction ───────────────────────────────────────────

interface Point {
  iso3: string;
  name: string;
  value: number;
  isImputed: boolean;
  region: string;
}

function scopeOk(p: { region: string; income_level?: string }): boolean {
  return (!state.region || p.region === state.region) && (!state.incomeLevel || p.income_level === state.incomeLevel);
}

function crossSection(shortName: string, year: number): Point[] {
  const out: Point[] = [];
  for (const [iso3, p] of Object.entries(DATA.profiles)) {
    if (!scopeOk(p)) continue;
    const trend = p.trends?.[shortName];
    const pt = trend?.find((t) => t.year === year);
    if (!pt || pt.value == null) continue;
    if (pt.is_imputed && !state.includeImputed) continue;
    out.push({ iso3, name: p.name, value: pt.value, isImputed: pt.is_imputed, region: p.region });
  }
  return out;
}

function africaAverageSeries(shortName: string, yearFrom: number, yearTo: number): { year: number; value: number }[] {
  const byYear: Record<number, number[]> = {};
  Object.values(DATA.profiles).forEach((p) => {
    if (!scopeOk(p)) return;
    (p.trends?.[shortName] || []).forEach((t) => {
      if (t.value == null || t.year < yearFrom || t.year > yearTo) return;
      if (t.is_imputed && !state.includeImputed) return;
      (byYear[t.year] ||= []).push(t.value);
    });
  });
  return Object.keys(byYear)
    .map(Number)
    .sort((a, b) => a - b)
    .map((year) => ({ year, value: byYear[year].reduce((a, b) => a + b, 0) / byYear[year].length }));
}

function natureBreakdown(points: { isImputed: boolean }[]): string {
  const obs = points.filter((p) => !p.isImputed).length;
  const imp = points.length - obs;
  return imp > 0 ? `${obs} observées, ${imp} imputées (ML)` : `${obs} observées`;
}

function unitLabel(ind: IndicatorMeta): string {
  return ind.unit ? ` (${ind.unit})` : "";
}

function formatShort(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n / 1e9).toFixed(1) + "Md";
  if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return n.toFixed(1);
}

// ── Header / stats-strip / methodology ────────────────────────

function setHeader(title: string, subtitle: string) {
  document.getElementById("chart-title")!.textContent = title;
  document.getElementById("chart-subtitle")!.textContent = subtitle;
}
function setStatsStrip(items: { label: string; value: string }[]) {
  document.getElementById("chart-stats-strip")!.innerHTML = items
    .map((i) => `<span class="px-2.5 py-1.5 rounded-full bg-surface-2 font-semibold"><span class="text-muted font-medium">${i.label} :</span> ${i.value}</span>`)
    .join("");
}
function setMethodology(text: string) {
  document.getElementById("chart-methodology-text")!.textContent = text;
  document.getElementById("chart-methodology")!.classList.remove("hidden");
}
function emptyMsg(msg: string): string {
  return `<div class="h-full flex items-center justify-center text-center text-sm text-muted px-6">${msg}</div>`;
}

// ── Render dispatch ────────────────────────────────────────────

function renderChartOnly() {
  document.getElementById("chart-empty")!.classList.add("hidden");
  const wrap = document.getElementById("chart-canvas-wrap")!;
  wrap.classList.remove("hidden");
  wrap.innerHTML = "";
  wrap.style.height = "";
  currentChart?.destroy();
  currentChart = null;
  currentCanvas = null;
  document.getElementById("chart-stats-strip")!.innerHTML = "";
  document.getElementById("chart-methodology")!.classList.add("hidden");

  try {
    if (state.analysis === "distribution") renderDistribution(wrap);
    else if (state.analysis === "comparison") renderComparison(wrap);
    else if (state.analysis === "correlation") renderCorrelation(wrap);
    else if (state.analysis === "evolution") renderEvolution(wrap);
    else if (state.analysis === "ranking") renderRanking(wrap);
  } catch (err) {
    console.error(err);
    wrap.innerHTML = emptyMsg("Impossible de générer ce graphique avec la sélection actuelle.");
  }
}

function makeCanvas(wrap: HTMLElement): HTMLCanvasElement {
  const c = document.createElement("canvas");
  wrap.appendChild(c);
  currentCanvas = c;
  return c;
}

function renderDistribution(wrap: HTMLElement) {
  const ind = indByShort(state.indicatorX)!;
  const points = crossSection(state.indicatorX, state.year);
  if (points.length < 3) {
    wrap.innerHTML = emptyMsg("Pas assez de données pour cette sélection (minimum 3 pays).");
    return;
  }
  const values = points.map((p) => p.value);

  if (state.chartType === "histogram") {
    const { edges, counts } = histogram(values);
    const labels = edges.slice(0, -1).map((e, i) => `${formatShort(e)}–${formatShort(edges[i + 1])}`);
    const canvas = makeCanvas(wrap);
    currentChart = new Chart(canvas.getContext("2d")!, {
      type: "bar",
      data: { labels, datasets: [{ label: "Nombre de pays", data: counts, backgroundColor: COLORS[0] + "cc", borderRadius: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: textColor(), font: { size: 11 }, maxRotation: 0, autoSkip: true }, grid: { display: false }, title: { display: true, text: ind.name + unitLabel(ind), color: textColor(), font: { size: 12, weight: "bold" } } },
          y: { ticks: { color: textColor(), precision: 0 }, grid: { color: gridColor() }, title: { display: true, text: "Nombre de pays", color: textColor() } },
        },
        plugins: { legend: { display: false } },
      },
    });
    const s = summarize(values);
    setHeader(`Distribution — ${ind.name}`, `${points.length} pays · ${state.year}`);
    setStatsStrip([
      { label: "Moyenne", value: formatValue(s.mean, ind.short_name) },
      { label: "Médiane", value: formatValue(s.median, ind.short_name) },
      { label: "Écart-type", value: formatValue(s.stdDev, ind.short_name) },
      { label: "Min–Max", value: `${formatValue(s.min, ind.short_name)} – ${formatValue(s.max, ind.short_name)}` },
    ]);
    setMethodology(`n = ${points.length} pays (${natureBreakdown(points)}) · répartition en ${sturgesBinCount(values.length)} classes (règle de Sturges).`);
  } else {
    const regions = [...new Set(points.map((p) => p.region))].sort();
    const dataByRegion = regions.map((r) => points.filter((p) => p.region === r).map((p) => p.value));
    const canvas = makeCanvas(wrap);
    currentChart = new Chart(canvas.getContext("2d")!, {
      type: state.chartType as "boxplot" | "violin",
      data: {
        labels: regions,
        datasets: [{ label: ind.name, data: dataByRegion, backgroundColor: COLORS.map((c) => c + "33"), borderColor: COLORS, borderWidth: 1.5 } as any],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: textColor(), font: { size: 11 } }, grid: { display: false } },
          y: { ticks: { color: textColor() }, grid: { color: gridColor() }, title: { display: true, text: ind.name + unitLabel(ind), color: textColor(), font: { size: 12, weight: "bold" } } },
        },
        plugins: { legend: { display: false } },
      } as any,
    });
    setHeader(`Distribution par région — ${ind.name}`, `${points.length} pays répartis en ${regions.length} régions · ${state.year}`);
    setStatsStrip([
      { label: "Régions", value: String(regions.length) },
      { label: "Pays", value: String(points.length) },
    ]);
    const chartLabel = state.chartType === "boxplot" ? "Boîte = médiane et quartiles (Q1–Q3) ; moustaches = 1,5×IQR ; points = valeurs atypiques" : "Largeur = densité estimée des valeurs (estimation par noyau)";
    setMethodology(`n = ${points.length} pays (${natureBreakdown(points)}) · ${chartLabel}.`);
  }
}

function renderComparison(wrap: HTMLElement) {
  const indX = indByShort(state.indicatorX)!;
  const indY = indByShort(state.indicatorY)!;
  const xs = crossSection(state.indicatorX, state.year);
  const ys = crossSection(state.indicatorY, state.year);
  const byIso3Y = new Map(ys.map((p) => [p.iso3, p]));
  const paired = xs.filter((p) => byIso3Y.has(p.iso3)).map((p) => ({ ...p, y: byIso3Y.get(p.iso3)!.value }));
  if (paired.length < 4) {
    wrap.innerHTML = emptyMsg("Pas assez de pays communs aux deux indicateurs pour cette sélection.");
    return;
  }

  const xVals = paired.map((p) => p.value);
  const yVals = paired.map((p) => p.y);
  const reg = linearRegression(xVals, yVals);
  const minX = Math.min(...xVals);
  const maxX = Math.max(...xVals);

  const canvas = makeCanvas(wrap);
  const datasets: any[] = [
    {
      type: state.chartType === "bubble" ? "bubble" : "scatter",
      label: `${indX.name} vs ${indY.name}`,
      data: paired.map((p) => ({ x: p.value, y: p.y, name: p.name })),
      backgroundColor: COLORS[0] + "bb",
      pointRadius: 5,
      pointHoverRadius: 7,
    },
  ];

  if (state.chartType === "bubble") {
    const pops = paired.map((p) => DATA.profiles[p.iso3]?.latest?.population || 0);
    const maxPop = Math.max(...pops, 1);
    datasets[0].data = paired.map((p, i) => ({ x: p.value, y: p.y, r: 5 + (pops[i] / maxPop) * 20, name: p.name }));
  } else {
    datasets.push({
      type: "line",
      label: "Régression linéaire",
      data: [
        { x: minX, y: reg.slope * minX + reg.intercept },
        { x: maxX, y: reg.slope * maxX + reg.intercept },
      ],
      borderColor: "#5A6C7D",
      borderDash: [6, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
    });
  }

  currentChart = new Chart(canvas.getContext("2d")!, {
    type: state.chartType === "bubble" ? "bubble" : "scatter",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: indX.name + unitLabel(indX), color: textColor(), font: { size: 12, weight: "bold" } }, ticks: { color: textColor() }, grid: { color: gridColor() } },
        y: { title: { display: true, text: indY.name + unitLabel(indY), color: textColor(), font: { size: 12, weight: "bold" } }, ticks: { color: textColor() }, grid: { color: gridColor() } },
      },
      plugins: {
        legend: { display: state.chartType !== "bubble", labels: { color: textColor() } },
        tooltip: {
          callbacks: {
            label: (c: any) => `${c.raw.name}: ${formatValue(c.raw.x, indX.short_name)}, ${formatValue(c.raw.y, indY.short_name)}`,
          },
        },
      },
    } as any,
  });

  setHeader(`${indX.name} vs ${indY.name}`, `${paired.length} pays · ${state.year}`);
  setStatsStrip([
    { label: "Corrélation (r)", value: reg.r.toFixed(2) },
    { label: "R²", value: reg.r2.toFixed(2) },
    { label: "n", value: String(paired.length) },
  ]);
  const extra = state.chartType === "bubble" ? "taille des bulles = population" : "droite = régression linéaire (moindres carrés)";
  setMethodology(`Corrélation de Pearson calculée sur ${paired.length} pays disposant des deux indicateurs pour ${state.year} · ${extra}.`);
}

function correlationColor(v: number): string {
  const clamped = Math.max(-1, Math.min(1, v));
  const stops: [number[], number[]] = clamped < 0 ? [[26, 58, 92], [244, 247, 252]] : [[244, 247, 252], [255, 107, 53]];
  const t = clamped < 0 ? clamped + 1 : clamped;
  const [r, g, b] = stops[0].map((c, i) => Math.round(c + t * (stops[1][i] - c)));
  return `rgb(${r},${g},${b})`;
}

function truncateLabel(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function wrapCanvasText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number) {
  const words = text.split(" ");
  let line = "";
  const lines: string[] = [];
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = w;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  const truncated = lines.slice(0, 2);
  const startY = y - ((truncated.length - 1) * lineHeight) / 2;
  truncated.forEach((l, i) => ctx.fillText(l, x, startY + i * lineHeight));
}

function drawHeatmap(canvas: HTMLCanvasElement, labels: string[], matrix: number[][]) {
  const n = labels.length;
  const cell = Math.max(46, Math.min(80, Math.floor(500 / n)));
  const leftW = 175;
  const topH = 125;
  const pad = 16;
  const width = leftW + cell * n + pad;
  const height = topH + cell * n + pad;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = width + "px";
  canvas.style.height = height + "px";
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = matrix[i][j];
      const x = leftW + j * cell;
      const y = topH + i * cell;
      ctx.fillStyle = isNaN(v) ? "#E4EBF2" : correlationColor(v);
      ctx.fillRect(x, y, cell - 3, cell - 3);
      ctx.fillStyle = !isNaN(v) && Math.abs(v) > 0.55 ? "#ffffff" : "#0A1628";
      ctx.font = "700 12px Inter, Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(isNaN(v) ? "–" : v.toFixed(2), x + (cell - 3) / 2, y + (cell - 3) / 2);
    }
  }

  ctx.fillStyle = "#0A1628";
  ctx.font = "600 11.5px Inter, Arial, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  labels.forEach((label, i) => {
    const y = topH + i * cell + (cell - 3) / 2;
    wrapCanvasText(ctx, truncateLabel(label, 30), leftW - 10, y, 160, 13);
  });

  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  labels.forEach((label, j) => {
    const x = leftW + j * cell + (cell - 3) / 2;
    ctx.save();
    ctx.translate(x, topH - 10);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(truncateLabel(label, 24), 0, 0);
    ctx.restore();
  });
}

function renderCorrelation(wrap: HTMLElement) {
  const keys = state.indicatorsMulti;
  if (keys.length < 3) {
    wrap.innerHTML = emptyMsg("Choisissez au moins 3 indicateurs pour une matrice de corrélation.");
    return;
  }
  const inds = keys.map((k) => indByShort(k)!);
  const valuesByKey: Record<string, Record<string, number>> = {};
  keys.forEach((k) => {
    valuesByKey[k] = {};
    crossSection(k, state.year).forEach((p) => {
      valuesByKey[k][p.iso3] = p.value;
    });
  });
  const { matrix } = correlationMatrix(valuesByKey);

  const canvas = document.createElement("canvas");
  wrap.appendChild(canvas);
  currentCanvas = canvas;
  drawHeatmap(canvas, inds.map((i) => i.name), matrix);

  let best = { i: 0, j: 1, v: 0 };
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix.length; j++) {
      if (i === j) continue;
      if (!isNaN(matrix[i][j]) && Math.abs(matrix[i][j]) > Math.abs(best.v)) best = { i, j, v: matrix[i][j] };
    }
  }

  setHeader("Matrice de corrélation", `${inds.length} indicateurs · ${state.year}`);
  setStatsStrip([{ label: "Corrélation la plus forte", value: `${inds[best.i].name} ↔ ${inds[best.j].name} (r=${best.v.toFixed(2)})` }]);
  setMethodology(
    `Corrélations de Pearson calculées par paire, chacune sur les pays disposant des deux indicateurs pour ${state.year} (suppression par paire des valeurs manquantes) · ${state.includeImputed ? "observées + imputées (ML)" : "valeurs observées uniquement"}.`
  );
}

function renderEvolution(wrap: HTMLElement) {
  const ind = indByShort(state.indicatorX)!;
  const canvas = makeCanvas(wrap);
  const datasets: any[] = [];

  if (state.countries.length === 0) {
    const series = africaAverageSeries(state.indicatorX, state.yearFrom, state.yearTo);
    if (series.length < 2) {
      wrap.innerHTML = emptyMsg("Pas assez de données pour cette période.");
      return;
    }
    datasets.push({ label: "Moyenne Afrique", data: series.map((t) => ({ x: t.year, y: t.value })), borderColor: COLORS[0], backgroundColor: COLORS[0] + "22", pointRadius: 2.5, tension: 0.3, fill: true });
  } else {
    state.countries.forEach((iso3, i) => {
      const color = COLORS[i % COLORS.length];
      const name = DATA.profiles[iso3]?.name || iso3;
      let trend = (DATA.profiles[iso3]?.trends?.[state.indicatorX] || []).filter((t) => t.year >= state.yearFrom && t.year <= state.yearTo);
      if (!state.includeImputed) trend = trend.filter((t) => !t.is_imputed);
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
    });
  }

  currentChart = new Chart(canvas.getContext("2d")!, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { type: "linear", title: { display: true, text: "Année", color: textColor() }, ticks: { color: textColor(), maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }, grid: { color: gridColor() } },
        y: { title: { display: true, text: ind.name + unitLabel(ind), color: textColor(), font: { size: 12, weight: "bold" } }, ticks: { color: textColor() }, grid: { color: gridColor() } },
      },
      plugins: { legend: { labels: { color: textColor(), boxWidth: 14, font: { size: 12, weight: "bold" } } } },
    } as any,
  });

  const scope = state.countries.length ? state.countries.map((c) => DATA.profiles[c]?.name).join(", ") : "Moyenne Afrique";
  setHeader(`Évolution — ${ind.name}`, `${scope} · ${state.yearFrom}–${state.yearTo}`);
  setMethodology(`Point plein = donnée observée · point clair = valeur imputée (ML)${state.includeImputed ? "" : " (imputations exclues)"}.`);
}

function renderRanking(wrap: HTMLElement) {
  const ind = indByShort(state.indicatorX)!;
  let points = crossSection(state.indicatorX, state.year);
  points = points.sort((a, b) => (state.rankOrder === "desc" ? b.value - a.value : a.value - b.value)).slice(0, state.rankTopN);
  if (!points.length) {
    wrap.innerHTML = emptyMsg("Aucune donnée pour cette sélection.");
    return;
  }
  wrap.style.height = Math.max(384, points.length * 24) + "px";

  const canvas = makeCanvas(wrap);
  currentChart = new Chart(canvas.getContext("2d")!, {
    type: "bar",
    data: {
      labels: points.map((p) => p.name),
      datasets: [{ label: ind.name, data: points.map((p) => p.value), backgroundColor: points.map((_, i) => COLORS[i % COLORS.length] + "cc"), borderRadius: 5 }],
    },
    options: {
      indexAxis: "y" as const,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: textColor() }, grid: { color: gridColor() }, title: { display: true, text: ind.name + unitLabel(ind), color: textColor() } },
        y: { ticks: { color: textColor(), font: { size: 11.5 } }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });

  setHeader(`Classement — ${ind.name}`, `${points.length} pays · ${state.year} · ${state.rankOrder === "desc" ? "valeurs les plus élevées" : "valeurs les plus faibles"}`);
  setMethodology(`n = ${points.length} pays (${natureBreakdown(points)}).`);
}

// ── Export ────────────────────────────────────────────────────

function exportCurrentPNG() {
  if (!currentCanvas) return;
  const composite = document.createElement("canvas");
  composite.width = currentCanvas.width;
  composite.height = currentCanvas.height;
  const ctx = composite.getContext("2d")!;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, composite.width, composite.height);
  ctx.drawImage(currentCanvas, 0, 0);
  const url = composite.toDataURL("image/png", 1.0);
  const a = document.createElement("a");
  a.href = url;
  a.download = `opendataviz-${state.analysis}-${state.chartType}.png`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

main();
