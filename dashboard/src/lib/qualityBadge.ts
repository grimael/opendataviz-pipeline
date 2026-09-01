import type { QualityReport } from "./types";

export function renderQualityBadge(quality: QualityReport): void {
  const qs = quality.overall_score;
  if (!qs) return;
  const scoreEl = document.getElementById("sidebar-quality-score");
  const barEl = document.getElementById("sidebar-quality-bar");
  if (scoreEl) scoreEl.textContent = String(qs);
  if (barEl) (barEl as HTMLElement).style.width = `${Math.min(100, qs)}%`;
}

// Sidebar is shared across every page (including ones that never load the
// full dashboard dataset, e.g. Données/Ressources/Assistant), so it fetches
// the quality report on its own rather than depending on a page-specific
// script to hand it the data.
export async function initSidebarQuality(): Promise<void> {
  try {
    const quality: QualityReport = await fetch("/data/quality_report.json").then((r) => r.json());
    renderQualityBadge(quality);
  } catch {
    // Leave the sidebar's placeholder "—" in place if this fails.
  }
}
