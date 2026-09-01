"""Shared helpers for API routes."""

import duckdb
from fastapi import HTTPException


def resolve_indicator_code(conn: duckdb.DuckDBPyConnection, indicator: str) -> str:
    """Resolve a path param that may be either the World Bank code
    (NY.GDP.MKTP.CD) or the dashboard-friendly short name (gdp) to the
    canonical indicator_code. 404s if neither matches."""
    row = conn.execute(
        "SELECT indicator_code FROM dim_indicator WHERE indicator_code = ? OR short_name = ?",
        [indicator, indicator.lower()],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator: {indicator!r}")
    return row[0]
