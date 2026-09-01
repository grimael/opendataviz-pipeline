"""OpenDataViz API — FastAPI entry point.

Run locally with:
    uvicorn api.main:app --reload

Swagger UI is auto-generated at /docs, ReDoc at /redoc.
"""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from .limiter import limiter
from .routes import agent, countries, data, export, health, indicators, projections

app = FastAPI(
    title="OpenDataViz API",
    description=(
        "REST API over the OpenDataViz observatory: 60 economic, health, education "
        "and infrastructure indicators for 54 African countries, sourced from the "
        "World Bank, gap-filled with ML imputation, and forecast 5 years ahead."
    ),
    version="1.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Trop de requêtes — réessaie dans un instant."})


# The dashboard is a separate static deployment (Vercel) on a different origin.
# Restrict to known origins rather than "*": /agent/chat proxies paid LLM calls
# and /export/* does non-trivial work per request, so any site should not be
# able to drive them from a visitor's browser. Override via ALLOWED_ORIGINS
# (comma-separated) for a real deployment; defaults cover local dev only.
_default_origins = "http://localhost:4321,http://127.0.0.1:4321"
allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(indicators.router)
app.include_router(countries.router)
app.include_router(data.router)
app.include_router(projections.router)
app.include_router(export.router)
app.include_router(health.router)
app.include_router(agent.router)


@app.get("/", tags=["health"])
def root():
    return {"name": "OpenDataViz API", "docs": "/docs", "health": "/health"}
