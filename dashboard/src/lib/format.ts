export function formatCurrency(n: number | null | undefined): string {
  if (!n) return "$0";
  if (n >= 1e12) return "$" + (n / 1e12).toFixed(1) + "T";
  if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
  return "$" + n.toLocaleString("en-US");
}

export function formatLargeNum(n: number | null | undefined): string {
  if (!n) return "0";
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toLocaleString("en-US");
}

const CURRENCY_INDICATORS = new Set(["gdp", "gdp_per_capita_ppp", "health_expenditure_capita"]);
const LARGE_NUM_INDICATORS = new Set(["population"]);

export function formatValue(v: number | null | undefined, shortName: string): string {
  if (v == null) return "N/A";
  if (CURRENCY_INDICATORS.has(shortName)) return formatCurrency(v);
  if (LARGE_NUM_INDICATORS.has(shortName)) return formatLargeNum(v);
  if (Math.abs(v) >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 1 });
  return v.toFixed(1);
}

export function downloadCSV(filename: string, headers: string[], rows: (string | number | null)[][]): void {
  const escape = (v: string | number | null) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [headers.join(","), ...rows.map((r) => r.map(escape).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
