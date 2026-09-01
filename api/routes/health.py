import json

import duckdb
from fastapi import APIRouter, Depends

from ..db import get_connection
from ..models import HealthStatus
from pipeline.config import DASHBOARD_DATA_DIR

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
def health(conn: duckdb.DuckDBPyConnection = Depends(get_connection)):
    """System status: DB connectivity, record counts, latest quality score."""
    total_facts, total_imputed = conn.execute(
        "SELECT COUNT(*), COUNT(CASE WHEN is_imputed THEN 1 END) FROM fact_indicators"
    ).fetchone()
    total_projections = conn.execute("SELECT COUNT(*) FROM projections").fetchone()[0]

    last_score, last_run = None, None
    quality_path = DASHBOARD_DATA_DIR / "quality_report.json"
    if quality_path.exists():
        report = json.loads(quality_path.read_text())
        last_score = report.get("overall_score")
        last_run = report.get("last_run")

    return HealthStatus(
        status="ok",
        database="connected",
        total_facts=total_facts,
        total_imputed=total_imputed,
        total_projections=total_projections,
        last_quality_score=last_score,
        last_quality_run=last_run,
    )
