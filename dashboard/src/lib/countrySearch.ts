import { loadDashboardData } from "./data";

declare global {
  interface Window {
    __openCountry?: (iso3: string) => void;
  }
}

async function main() {
  const input = document.getElementById("global-country-search") as HTMLInputElement | null;
  const results = document.getElementById("global-country-search-results");
  if (!input || !results) return;

  const data = await loadDashboardData();
  const entries = Object.entries(data.profiles);

  function render(query: string) {
    const q = query.trim().toLowerCase();
    if (!q) {
      results!.classList.add("hidden");
      results!.innerHTML = "";
      return;
    }
    const matches = entries.filter(([, p]) => p.name.toLowerCase().includes(q)).slice(0, 6);
    if (!matches.length) {
      results!.innerHTML = `<div class="px-3.5 py-3 text-sm text-muted">Aucun pays trouvé</div>`;
      results!.classList.remove("hidden");
      return;
    }
    results!.innerHTML = matches
      .map(
        ([iso3, p]) => `
      <button type="button" data-iso3="${iso3}" class="w-full flex items-center justify-between gap-2 px-3.5 py-2.5 text-left text-sm hover:bg-surface-2 transition-colors">
        <span class="font-medium">${p.name}</span>
        <span class="text-xs text-muted">${p.region}</span>
      </button>`
      )
      .join("");
    results!.classList.remove("hidden");
  }

  input.addEventListener("input", () => render(input.value));
  input.addEventListener("focus", () => render(input.value));
  document.addEventListener("click", (e) => {
    if (!(e.target instanceof Node)) return;
    if (!results!.contains(e.target) && e.target !== input) results!.classList.add("hidden");
  });

  results.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-iso3]");
    if (!btn) return;
    const iso3 = btn.dataset.iso3!;
    if (window.__openCountry) {
      window.__openCountry(iso3);
      results.classList.add("hidden");
      input.value = "";
    } else {
      window.location.href = `/?openCountry=${iso3}`;
    }
  });
}

main();
