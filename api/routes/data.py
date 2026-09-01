from fastapi import APIRouter, Depends, Query
import duckdb

from ..db import get_connection
from ..models import DataPoint
from ..utils import resolve_indicator_code

router = APIRouter(tags=["data"])


@router.get("/data/{indicator_code}", response_model=list[DataPoint])
def get_indicator_data(
    indicator_code: str,
    country: list[str] | None = Query(None, description="ISO3 codes to filter, repeatable: ?country=KEN&country=NGA"),
    year_from: int | None = Query(None, ge=1900),
    year_to: int | None = Query(None, le=2100),
    include_imputed: bool = Query(True, description="Set false to return only genuinely-observed values"),
    conn: duckdb.DuckDBPyConnection = Depends(get_connection),
):
    """Historical data for one indicator (World Bank code or short name), real + ML-imputed, flagged."""
    code = resolve_indicator_code(conn, indicator_code)

    query = """
        SELECT dc.iso3_code, dc.country_name, dd.year, f.value, f.is_imputed, f.imputation_method
        FROM fact_indicators f
        JOIN dim_country dc ON f.country_key = dc.country_key
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        JOIN dim_date dd ON f.date_key = dd.date_key
        WHERE di.indicator_code = ?
    """
    params: list = [code]

    if country:
        placeholders = ",".join("?" for _ in country)
        query += f" AND dc.iso3_code IN ({placeholders})"
        params += [c.upper() for c in country]
    if year_from is not None:
        query += " AND dd.year >= ?"
        params.append(year_from)
    if year_to is not None:
        query += " AND dd.year <= ?"
        params.append(year_to)
    if not include_imputed:
        query += " AND NOT f.is_imputed"

    query += " ORDER BY dc.country_name, dd.year"
    rows = conn.execute(query, params).fetchall()

    return [
        DataPoint(country_iso3=r[0], country_name=r[1], year=r[2], value=r[3], is_imputed=bool(r[4]), imputation_method=r[5])
        for r in rows
    ]
