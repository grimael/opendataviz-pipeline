from fastapi import APIRouter, Depends, Query
import duckdb

from ..db import get_connection
from ..models import CountryOut

router = APIRouter(tags=["countries"])


@router.get("/countries", response_model=list[CountryOut])
def list_countries(
    region: str | None = Query(None, description="Filter to one region, e.g. 'West Africa'"),
    conn: duckdb.DuckDBPyConnection = Depends(get_connection),
):
    """List all 54 African countries with region and income-level metadata."""
    query = (
        "SELECT iso3_code, iso2_code, country_name, region, income_level, capital_city, latitude, longitude "
        "FROM dim_country"
    )
    params: list[str] = []
    if region:
        query += " WHERE region = ?"
        params.append(region)
    query += " ORDER BY country_name"

    rows = conn.execute(query, params).fetchall()
    return [
        CountryOut(
            iso3=r[0], iso2=r[1], name=r[2], region=r[3],
            income_level=r[4], capital_city=r[5], latitude=r[6], longitude=r[7],
        )
        for r in rows
    ]
