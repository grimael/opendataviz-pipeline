from fastapi import APIRouter, Depends, HTTPException, Query
import duckdb

from ..db import get_connection
from ..models import IndicatorOut
from pipeline.config import POLES

router = APIRouter(tags=["indicators"])


@router.get("/indicators", response_model=dict[str, list[IndicatorOut]])
def list_indicators(
    pole: str | None = Query(None, description=f"Filter to one pole: {', '.join(POLES)}"),
    conn: duckdb.DuckDBPyConnection = Depends(get_connection),
):
    """List indicators grouped by pole (Economy / Health / Education / Infrastructure)."""
    if pole and pole not in POLES:
        raise HTTPException(status_code=400, detail=f"Unknown pole {pole!r}. Expected one of {POLES}")

    query = "SELECT indicator_code, indicator_name, category, unit, short_name FROM dim_indicator"
    params: list[str] = []
    if pole:
        query += " WHERE category = ?"
        params.append(pole)
    query += " ORDER BY category, indicator_name"

    rows = conn.execute(query, params).fetchall()
    grouped: dict[str, list[IndicatorOut]] = {p: [] for p in ([pole] if pole else POLES)}
    for code, name, category, unit, short in rows:
        grouped.setdefault(category, []).append(
            IndicatorOut(code=code, name=name, category=category, unit=unit, short_name=short)
        )
    return grouped
