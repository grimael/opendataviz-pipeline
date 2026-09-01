import { loadDashboardData } from "./data";
import { formatValue } from "./format";
import type { DashboardData, IndicatorMeta } from "./types";

declare global {
  interface Window {
    __INDICATORS_BY_POLE__: Record<string, IndicatorMeta[]>;
    __API_BASE_URL__: string;
    __EXPORT_FORMATS__: { id: string; label: string; hint: string }[];
  }
}

const INDICATORS_BY_POLE = window.__INDICATORS_BY_POLE__;
const API_BASE_URL = window.__API_BASE_URL__;
const FORMATS = window.__EXPORT_FORMATS__;

let DATA: DashboardData;

async function main() {
  DATA = await loadDashboardData();

  const poleSelect = document.getElementById("data-pole") as HTMLSelectElement;
  const indicatorSelect = document.getElementById("data-indicator") as HTMLSelectElement;

  const requestedPole = new URLSearchParams(location.search).get("pole");
  if (requestedPole && INDICATORS_BY_POLE[requestedPole]) {
    poleSelect.value = requestedPole;
  }

  populateIndicatorOptions(poleSelect.value);
  poleSelect.addEventListener("change", () => {
    populateIndicatorOptions(poleSelect.value);
    render();
  });
  indicatorSelect.addEventListener("change", render);

  renderDownloadButtons();
  render();
}

function populateIndicatorOptions(pole: string) {
  const indicatorSelect = document.getElementById("data-indicator") as HTMLSelectElement;
  const list = INDICATORS_BY_POLE[pole] || [];
  indicatorSelect.innerHTML = list.map((ind) => `<option value="${ind.short_name}">${ind.name}</option>`).join("");
}

function currentIndicator(): IndicatorMeta | undefined {
  const pole = (document.getElementById("data-pole") as HTMLSelectElement).value;
  const shortName = (document.getElementById("data-indicator") as HTMLSelectElement).value;
  return (INDICATORS_BY_POLE[pole] || []).find((i) => i.short_name === shortName);
}

function render() {
  const ind = currentIndicator();
  if (!ind) return;
  renderPreview(ind);
  renderDownloadButtons();
}

function renderPreview(ind: IndicatorMeta) {
  const rows: { country: string; year: number; value: number | null; is_imputed: boolean }[] = [];
  Object.values(DATA.profiles).forEach((p) => {
    (p.trends?.[ind.short_name] || []).forEach((t) => {
      rows.push({ country: p.name, year: t.year, value: t.value, is_imputed: t.is_imputed });
    });
  });
  rows.sort((a, b) => a.country.localeCompare(b.country) || a.year - b.year);

  const observed = rows.filter((r) => !r.is_imputed).length;
  const imputed = rows.filter((r) => r.is_imputed).length;
  const summary = document.getElementById("preview-summary")!;
  summary.innerHTML = `
    <span class="px-2.5 py-1 rounded-full bg-surface-2 font-semibold">${rows.length} lignes</span>
    <span class="px-2.5 py-1 rounded-full bg-economy-soft text-economy font-semibold">${observed} observées</span>
    <span class="px-2.5 py-1 rounded-full bg-infrastructure-soft text-infrastructure font-semibold">${imputed} imputées</span>
  `;

  const body = document.getElementById("preview-body")!;
  // Cap the DOM preview for performance; full data is in the downloads below.
  const preview = rows.slice(0, 300);
  body.innerHTML = preview
    .map(
      (r) => `<tr class="border-b border-border last:border-0">
      <td class="py-2 px-3 font-medium">${r.country}</td>
      <td class="py-2 px-3 tabular-nums">${r.year}</td>
      <td class="py-2 px-3 text-right tabular-nums">${r.value != null ? formatValue(r.value, ind.short_name) : "—"}</td>
      <td class="py-2 px-3">${r.is_imputed ? '<span class="text-infrastructure font-semibold">Imputée (ML)</span>' : '<span class="text-muted">Observée</span>'}</td>
    </tr>`
    )
    .join("");
  if (rows.length > preview.length) {
    body.innerHTML += `<tr><td colspan="4" class="py-2.5 px-3 text-center text-xs text-muted">… ${rows.length - preview.length} lignes supplémentaires — téléchargez le fichier complet ci-dessous</td></tr>`;
  }
}

function renderDownloadButtons() {
  const ind = currentIndicator();
  if (!ind) return;

  const build = (scope: "observed" | "all") =>
    FORMATS.map(
      (f) => `
      <a
        href="${API_BASE_URL}/export/${ind.code}?format=${f.id}&scope=${scope}"
        class="group flex flex-col items-center justify-center gap-2 rounded-xl border border-border bg-surface-2 hover:bg-surface hover:border-brand-light hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 py-3.5 text-center"
      >
        <svg width="34" height="34" class="drop-shadow-sm"><use href="#ic-filetype-${f.id}"/></svg>
        <span class="text-[10.5px] text-muted font-medium leading-tight">${f.hint}</span>
      </a>`
    ).join("");

  document.getElementById("download-observed")!.innerHTML = build("observed");
  document.getElementById("download-all")!.innerHTML = build("all");
}

main();
