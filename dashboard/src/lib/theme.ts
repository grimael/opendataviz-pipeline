// Single light theme only — no dark mode toggle. Kept as a no-op module so
// existing imports don't need to change if theming returns later.
export function initTheme(): void {}

export function isDark(): boolean {
  return false;
}

export const INLINE_THEME_SCRIPT = "";
