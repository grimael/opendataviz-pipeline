"""Data quality framework — completeness, validity, freshness checks."""

import duckdb
import logging
from datetime import datetime, timezone
from typing import Any

from .config import DB_PATH, INDICATORS, DQ_THRESHOLDS, AFRICAN_COUNTRIES

logger = logging.getLogger(__name__)


def run_quality_checks() -> dict[str, Any]:
    """Run all data quality checks and return a structured report."""
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        report = {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "dimensions": {},
            "overall_score": 0,
        }
        
        completeness = _check_completeness(conn)
        validity = _check_validity(conn)
        freshness = _check_freshness(conn)
        summary = _get_summary_stats(conn)
        imputation = _get_imputation_stats(conn)

        report["dimensions"]["completeness"] = completeness
        report["dimensions"]["validity"] = validity
        report["dimensions"]["freshness"] = freshness
        report.update(summary)
        report["imputation"] = imputation
        
        # Overall score = weighted average
        scores = [
            completeness["score"] * 0.35,
            validity["score"] * 0.35,
            freshness["score"] * 0.30,
        ]
        report["overall_score"] = round(sum(scores), 1)
        
        logger.info(f"Data quality score: {report['overall_score']}/100")
        return report
    finally:
        conn.close()


def _check_completeness(conn: duckdb.DuckDBPyConnection) -> dict:
    """Check what % of expected data points are genuinely observed (non-null,
    non-imputed). Imputed values are excluded on purpose: completeness measures
    real World Bank coverage, not what ML imputation later fills in — see
    _get_imputation_stats for imputation coverage."""
    results = conn.execute("""
        SELECT
            di.indicator_code,
            di.indicator_name,
            COUNT(*) as total_records,
            COUNT(CASE WHEN f.value IS NOT NULL AND NOT f.is_imputed THEN 1 END) as non_null_records,
            ROUND(COUNT(CASE WHEN f.value IS NOT NULL AND NOT f.is_imputed THEN 1 END) * 100.0 / COUNT(*), 1) as completeness_pct
        FROM fact_indicators f
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        GROUP BY di.indicator_code, di.indicator_name
        ORDER BY completeness_pct
    """).fetchall()
    
    details = []
    scores = []
    for code, name, total, non_null, pct in results:
        details.append({
            "indicator": code,
            "name": name,
            "total_records": total,
            "non_null": non_null,
            "completeness_pct": pct,
            "status": "pass" if pct >= 50 else "warn" if pct >= 25 else "fail",
        })
        scores.append(pct)
    
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    return {"score": avg_score, "details": details}


def _check_validity(conn: duckdb.DuckDBPyConnection) -> dict:
    """Check if values fall within expected ranges."""
    details = []
    scores = []
    
    for code, thresh in DQ_THRESHOLDS.items():
        result = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN f.value >= ? AND f.value <= ? THEN 1 END) as valid,
                COUNT(CASE WHEN f.value < ? OR f.value > ? THEN 1 END) as invalid
            FROM fact_indicators f
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            WHERE di.indicator_code = ? AND f.value IS NOT NULL
        """, [thresh["min"], thresh["max"], thresh["min"], thresh["max"], code]).fetchone()
        
        total, valid, invalid = result
        pct = round(valid * 100.0 / total, 1) if total > 0 else 100
        details.append({
            "indicator": code,
            "name": INDICATORS[code]["name"],
            "total_checked": total,
            "valid": valid,
            "invalid": invalid,
            "valid_pct": pct,
            "range": f"[{thresh['min']}, {thresh['max']}]",
            "status": "pass" if pct >= 95 else "warn" if pct >= 80 else "fail",
        })
        scores.append(pct)
    
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    return {"score": avg_score, "details": details}


def _check_freshness(conn: duckdb.DuckDBPyConnection) -> dict:
    """Check how recent the data is for each indicator."""
    results = conn.execute("""
        SELECT 
            di.indicator_code,
            di.indicator_name,
            MAX(dd.year) as latest_year,
            COUNT(DISTINCT dc.iso3_code) as countries_with_data
        FROM fact_indicators f
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        JOIN dim_date dd ON f.date_key = dd.date_key
        JOIN dim_country dc ON f.country_key = dc.country_key
        WHERE f.value IS NOT NULL
        GROUP BY di.indicator_code, di.indicator_name
        ORDER BY latest_year DESC
    """).fetchall()
    
    details = []
    scores = []
    for code, name, latest_year, countries in results:
        # Score based on how recent: 2024=100, 2023=90, 2022=80, etc.
        year_score = max(0, 100 - (2024 - latest_year) * 10)
        details.append({
            "indicator": code,
            "name": name,
            "latest_year": latest_year,
            "countries_with_data": countries,
            "status": "pass" if latest_year >= 2022 else "warn" if latest_year >= 2020 else "fail",
        })
        scores.append(year_score)
    
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    return {"score": avg_score, "details": details}


def _get_imputation_stats(conn: duckdb.DuckDBPyConnection) -> dict:
    """Report how much of the warehouse's non-null data was ML-imputed vs observed."""
    row = conn.execute("""
        SELECT
            COUNT(CASE WHEN value IS NOT NULL THEN 1 END) as non_null,
            COUNT(CASE WHEN is_imputed THEN 1 END) as imputed
        FROM fact_indicators
    """).fetchone()
    non_null, imputed = row
    pct = round(imputed * 100.0 / non_null, 1) if non_null else 0

    by_method = conn.execute("""
        SELECT imputation_method, COUNT(*)
        FROM fact_indicators
        WHERE is_imputed
        GROUP BY imputation_method
    """).fetchall()

    return {
        "non_null_records": non_null,
        "imputed_records": imputed,
        "observed_records": non_null - imputed,
        "imputed_pct": pct,
        "by_method": {method: count for method, count in by_method},
    }


def _get_summary_stats(conn: duckdb.DuckDBPyConnection) -> dict:
    """Get overall summary statistics."""
    total_records = conn.execute("SELECT COUNT(*) FROM fact_indicators").fetchone()[0]
    non_null = conn.execute("SELECT COUNT(*) FROM fact_indicators WHERE value IS NOT NULL").fetchone()[0]
    countries = conn.execute("SELECT COUNT(DISTINCT country_key) FROM fact_indicators WHERE value IS NOT NULL").fetchone()[0]
    indicators = conn.execute("SELECT COUNT(DISTINCT indicator_key) FROM fact_indicators").fetchone()[0]
    year_range = conn.execute("SELECT MIN(date_key), MAX(date_key) FROM fact_indicators WHERE value IS NOT NULL").fetchone()
    
    return {
        "total_records": total_records,
        "non_null_records": non_null,
        "countries_covered": countries,
        "indicators_checked": indicators,
        "year_range": f"{year_range[0]}-{year_range[1]}" if year_range[0] else "N/A",
    }
