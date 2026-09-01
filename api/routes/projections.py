from fastapi import APIRouter, Depends, Query
import duckdb

from ..db import get_connection
from ..models import ProjectionPoint
from ..utils import resolve_indicator_code

router = APIRouter(tags=["projections"])


@router.get("/projections/{indicator_code}", response_model=list[ProjectionPoint])
def get_indicator_projections(
    indicator_code: str,
    country: list[str] | None = Query(None, description="ISO3 codes to filter, repeatable: ?country=KEN&country=NGA"),
    conn: duckdb.DuckDBPyConnection = Depends(get_connection),
):
    """5-year-ahead ElasticNet forecast for one indicator, with in-sample R^2 per country."""
    code = resolve_indicator_code(conn, indicator_code)

    query = """
        SELECT dc.iso3_code, dc.country_name, p.year, p.projected_value, p.method, p.confidence
        FROM projections p
        JOIN dim_country dc ON p.country_key = dc.country_key
        JOIN dim_indicator di ON p.indicator_key = di.indicator_key
        WHERE di.indicator_code = ?
    """
    params: list = [code]
    if country:
        placeholders = ",".join("?" for _ in country)
        query += f" AND dc.iso3_code IN ({placeholders})"
        params += [c.upper() for c in country]
    query += " ORDER BY dc.country_name, p.year"

    rows = conn.execute(query, params).fetchall()
    return [
        ProjectionPoint(country_iso3=r[0], country_name=r[1], year=r[2], projected_value=r[3], method=r[4], confidence=r[5])
        for r in rows
    ]
