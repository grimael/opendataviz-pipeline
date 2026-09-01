import csv
import io
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..db import get_connection
from ..limiter import limiter
from ..utils import resolve_indicator_code

router = APIRouter(tags=["export"])

_COLUMNS = ["iso3", "country", "year", "value", "is_imputed", "imputation_method"]
_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "dta": "application/octet-stream",
    "sav": "application/octet-stream",
    "parquet": "application/octet-stream",
}


@router.get("/export/{indicator_code}")
@limiter.limit("20/minute")
def export_indicator(
    request: Request,
    indicator_code: str,
    format: str = Query("csv", pattern="^(csv|xlsx|dta|sav|parquet)$"),
    scope: str = Query("all", pattern="^(all|observed)$", description="'observed' = raw World Bank values only, 'all' = observed + ML-imputed"),
    conn: duckdb.DuckDBPyConnection = Depends(get_connection),
):
    """Download full history for one indicator as CSV, Excel, Stata, SPSS or Parquet.

    `scope=observed` gives the raw World Bank series (what the source actually
    published — gaps included); `scope=all` (default) fills those gaps with
    the ML-imputed values, still flagged via `is_imputed`."""
    code = resolve_indicator_code(conn, indicator_code)

    query = """
        SELECT dc.iso3_code, dc.country_name, dd.year, f.value, f.is_imputed, f.imputation_method
        FROM fact_indicators f
        JOIN dim_country dc ON f.country_key = dc.country_key
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        JOIN dim_date dd ON f.date_key = dd.date_key
        WHERE di.indicator_code = ?
    """
    params = [code]
    if scope == "observed":
        query += " AND NOT f.is_imputed"
    query += " ORDER BY dc.country_name, dd.year"

    rows = conn.execute(query, params).fetchall()
    filename_base = f"{indicator_code.lower().replace('.', '_')}_{scope}"
    media_type = _MEDIA_TYPES[format]
    headers = {"Content-Disposition": f'attachment; filename="{filename_base}.{format}"'}

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_COLUMNS)
        writer.writerows(rows)
        return StreamingResponse(iter([buf.getvalue()]), media_type=media_type, headers=headers)

    df = pd.DataFrame(rows, columns=_COLUMNS)

    if format == "parquet":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type=media_type, headers=headers)

    # Excel/Stata/SPSS writers need a real file path (no in-memory buffer
    # support), so round-trip through a temp file rather than StreamingResponse.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"export.{format}"
        if format == "xlsx":
            df.to_excel(path, index=False, sheet_name=indicator_code[:31])
        elif format == "dta":
            # Stata has no native bool/NULL-string type: normalize before writing.
            stata_df = df.copy()
            stata_df["imputation_method"] = stata_df["imputation_method"].fillna("")
            stata_df.to_stata(path, write_index=False, version=118)
        elif format == "sav":
            import pyreadstat

            sav_df = df.copy()
            sav_df["is_imputed"] = sav_df["is_imputed"].astype(int)
            sav_df["imputation_method"] = sav_df["imputation_method"].fillna("")
            pyreadstat.write_sav(sav_df, str(path))
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")

        data = path.read_bytes()

    return StreamingResponse(iter([data]), media_type=media_type, headers=headers)
