// The dashboard itself stays a static site (public/data/*.json) — this is
// only used for live queries: the Données page's download links, the
// "API publique" sidebar link, and the Assistant IA chat.
//
// In dev, astro.config.mjs proxies /api/* to the FastAPI service on
// localhost:8000, so the browser only ever talks to one origin
// (localhost:4321) — no second port to remember, no CORS.
//
// In production there's no dev proxy, so the API's public URL must be baked
// in at build time via the PUBLIC_API_BASE_URL env var (e.g.
// "https://opendataviz-api.onrender.com") — falls back to the dev-only "/api"
// proxy path if unset.
export const API_BASE_URL = import.meta.env.PUBLIC_API_BASE_URL || "/api";
