# Security

This document records the security review of OpenDataViz's backend and frontend, what it found, what was changed as a result, and how to configure the hardening for a real deployment. It's meant to be read by whoever runs this API next — including future-you.

## Scope

Reviewed: every route under `api/`, the DuckDB access layer, the LLM/agent integration, the export pipeline, the pipeline's outbound World Bank API calls, the dependency manifest, and every dynamic-HTML call site in the dashboard's TypeScript (`innerHTML` usage across `home-app.ts`, `pole-app.ts`, `data-page.ts`, `statistics-app.ts`, `assistant-app.ts`, `countrySearch.ts`).

Not in scope: the hosting platform's own security (Vercel, wherever the API ends up deployed), the World Bank's API itself, and the LLM providers' (Groq/Gemini) own infrastructure.

## What was already solid

- **SQL injection**: every query in `api/routes/*.py` and `api/agent_tools.py` is parameterized. The only string-building that happens is constructing `?`-placeholder skeletons (`",".join("?" for _ in items)`) for `IN (...)` clauses — never a request value spliced into SQL text.
- **Read-only DB access**: `api/db.py` opens a fresh, read-only DuckDB connection per request and closes it immediately, so the API process can never corrupt the warehouse or collide with the nightly ETL write.
- **Secrets hygiene**: `.env` (the only place real LLM keys live) is gitignored; `.env.example` ships empty. Verified via `git check-ignore -v .env` and `git status --porcelain` that neither has ever been tracked.
- **XSS**: the one place LLM/user-influenced content reaches the DOM (`dashboard/src/lib/assistant-app.ts`) escapes all HTML first (`escapeHtml()`) before re-introducing a restricted, hand-parsed Markdown subset (`**bold**`, `- ` bullets). Every other `innerHTML` assignment across the dashboard interpolates only static, build-time JSON (indicator names, country names, region labels) — never a raw user-typed string. No `eval`, `Function()`, `document.write`, or `dangerouslySetInnerHTML` anywhere in the codebase.
- **Outbound requests** (`pipeline/extract.py`): every World Bank API call has an explicit 60s timeout and bounded exponential-backoff retries (max 3 attempts) — no unbounded hang, no retry storm.
- **Export format/scope validation**: `format` and `scope` on `GET /export/{indicator}` are constrained by FastAPI `Query(pattern=...)` regexes before anything touches pandas — an invalid value is rejected with 422 before any file is built.
- **CSV/formula-injection risk on export**: reviewed and judged negligible. The only string field in an export (`country_name`) comes from a fixed, 54-row dimension table populated entirely by the ETL pipeline — never from request input — so a leading `=`/`+`/`-`/`@` can't be injected by a caller. No sanitization was added; there was nothing to sanitize.

## What was found and fixed

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | CORS allowed every origin (`allow_origins=["*"]`) on an API with two costly endpoints — `/agent/chat` (paid LLM call) and `/export/*` (per-request file generation) | High | Restricted to an explicit allow-list, configurable via `ALLOWED_ORIGINS` (comma-separated) in `.env`; defaults to the local dashboard dev origin only. See `api/main.py`. |
| 2 | No rate limiting anywhere — a single client could hammer `/agent/chat` (burns LLM quota/cost) or `/export/*` (repeated file generation) with no limit | High | Added `slowapi`, limited to 10 requests/minute on `POST /agent/chat` and 20/minute on `GET /export/{indicator}`, per client IP. Exceeding it returns a clean `429` instead of the default handler's stack-trace-shaped body. |
| 3 | No size limit on `/agent/chat` request bodies — an arbitrarily long `message` or `history` gets forwarded straight into the LLM prompt, at the caller's leisure and the project owner's expense | Medium | `ChatRequest.message` capped at 2000 chars, `history` capped at 12 messages of 2000 chars each, enforced by Pydantic `Field(max_length=...)` — rejected with `422` before any LLM call is made. |
| 4 | Raw Python exception text returned to the client: `api/db.py`'s 503 handler interpolated the DuckDB exception directly into `detail`; `api/agent_tools.py`'s `execute_tool()` did the same into a dict the LLM (and transitively the chat reply) could surface | Low–Medium | Both now log the full exception server-side (`logger.exception(...)`) and return a short, generic, non-leaking message to the caller. |
| 5 | No request timeout on the LLM client — a hung provider connection could tie up a request/worker indefinitely | Low | `OpenAI(...)` client in `api/llm.py` now sets `timeout=30.0, max_retries=1`. |
| 6 | Missing baseline security response headers | Low | Added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` via a small middleware in `api/main.py`. |
| 7 | Unpinned dependency floors (`>=` everywhere in `requirements.txt`/`pyproject.toml`) — a future transitive release could silently change behavior or introduce a vulnerability with no review | Low | Documented here rather than blind-pinned (pinning without testing each exact version against this codebase would trade one risk for another). **Recommendation**: before a production deploy, generate and commit a lockfile (`pip freeze > requirements.lock.txt` from a known-good environment, or migrate to `uv`/`pip-tools`) and add `pip-audit` or GitHub's Dependabot to CI. |

No authentication/authorization layer exists on any route, by design — every route is read-only public data (or, for `/agent/chat`, a read-only query interface over that same data). If this API is ever extended with write operations or non-public data, it needs real auth before that ships; nothing here should be read as "the API doesn't need auth" as a general rule, only as "it doesn't currently expose anything that requires it."

## Configuring the hardening

**CORS** — set `ALLOWED_ORIGINS` in `.env` to your real deployed dashboard origin(s) before going to production:

```bash
ALLOWED_ORIGINS=https://your-dashboard.vercel.app
```

Never set it back to `*` in production — `/agent/chat` and `/export/*` both do real, costly work per request.

**Rate limits** — defined inline as decorators (`@limiter.limit("10/minute")` on `/agent/chat`, `@limiter.limit("20/minute")` on `/export/{indicator}`, in `api/routes/agent.py` / `api/routes/export.py`). Adjust there if real traffic patterns need different numbers. The limiter (`api/limiter.py`) keys on client IP and stores counters in-process — fine for a single-instance deployment; if this ever runs behind a load balancer with multiple workers, point `slowapi`/`limits` at a shared Redis backend instead, or the per-instance counters will under-count.

**Message/history caps** — `MAX_MESSAGE_LENGTH` and `MAX_HISTORY_MESSAGES` at the top of `api/routes/agent.py`.

## Reporting an issue

This is a personal/small-team project without a formal bug-bounty program. If you find a security issue, open a GitHub issue with enough detail to reproduce it, or reach out directly if it's sensitive enough that it shouldn't be public before a fix ships.
