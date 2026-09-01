// The dashboard itself stays a static site (public/data/*.json) — this is
// only used for live queries: the Données page's download links, the
// "API publique" sidebar link, and the Assistant IA chat.
//
// In dev, astro.config.mjs proxies /api/* to the FastAPI service on
// localhost:8000, so the browser only ever talks to one origin
// (localhost:4321) — no second port to remember, no CORS.
//
// In production, either deploy an equivalent rewrite in front of the static
// site (so /api/* still reaches the API), or replace this with the API's
// public URL (e.g. "https://api.opendataviz.example").
export const API_BASE_URL = "/api";
