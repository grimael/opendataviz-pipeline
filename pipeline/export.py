"""Export DuckDB data to JSON files for the static dashboard."""

import json
import duckdb
import logging
from typing import Any

from .config import DB_PATH, DASHBOARD_DATA_DIR, INDICATORS, AFRICAN_COUNTRIES, POLES

logger = logging.getLogger(__name__)


def export_all() -> None:
    """Export all dashboard data files."""
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        _export_indicators_meta(conn)
        _export_country_profiles(conn)
        _export_rankings(conn)
        _export_summary_stats(conn)
        _export_projections(conn)
        logger.info("All dashboard data exported successfully")
    finally:
        conn.close()


def _export_indicators_meta(conn: duckdb.DuckDBPyConnection) -> None:
    """Export indicator catalog grouped by pole — lets the dashboard build
    dropdowns/optgroups dynamically instead of hardcoding indicator lists in
    HTML (which is how the map/compare/rankings selectors ended up only
    covering 9 of the original 10 indicators before this catalog existed)."""
    grouped: dict[str, list[dict]] = {pole: [] for pole in POLES}
    for code, meta in INDICATORS.items():
        grouped[meta["category"]].append({
            "code": code,
            "short_name": meta["short"],
            "name": meta["name"],
            "unit": meta["unit"],
        })
    for pole in grouped:
        grouped[pole].sort(key=lambda i: i["name"])

    path = DASHBOARD_DATA_DIR / "indicators.json"
    with open(path, "w") as f:
        json.dump(grouped, f, indent=2)
    logger.info(f"Exported indicator catalog ({len(INDICATORS)} indicators, {len(POLES)} poles)")


def export_quality_report(report: dict) -> None:
    """Write quality report JSON to dashboard data directory."""
    path = DASHBOARD_DATA_DIR / "quality_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"Quality report exported to {path}")


def _export_country_profiles(conn: duckdb.DuckDBPyConnection) -> None:
    """Export comprehensive country profiles with latest values and trends."""
    profiles: dict[str, dict] = {}
    
    # Get country metadata
    countries = conn.execute("""
        SELECT iso3_code, country_name, region, income_level, capital_city, latitude, longitude
        FROM dim_country
    """).fetchall()
    
    for iso3, name, region, income, capital, lat, lng in countries:
        profiles[iso3] = {
            "name": name,
            "iso3": iso3,
            "iso2": AFRICAN_COUNTRIES.get(iso3, {}).get("iso2", ""),
            "region": region,
            "income_level": income or "Unknown",
            "capital_city": capital or "",
            "lat": lat or 0,
            "lng": lng or 0,
            "latest": {},
            "latest_is_imputed": {},
            "trends": {},
        }
    
    # Get all indicator data grouped by country
    data = conn.execute("""
        SELECT
            dc.iso3_code,
            di.short_name,
            di.indicator_code,
            dd.year,
            f.value,
            f.yoy_change,
            f.is_imputed
        FROM fact_indicators f
        JOIN dim_country dc ON f.country_key = dc.country_key
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        JOIN dim_date dd ON f.date_key = dd.date_key
        ORDER BY dc.iso3_code, di.short_name, dd.year
    """).fetchall()

    for iso3, short_name, ind_code, year, value, yoy, is_imputed in data:
        if iso3 not in profiles:
            continue

        # Build trends
        if short_name not in profiles[iso3]["trends"]:
            profiles[iso3]["trends"][short_name] = []
        if value is not None:
            profiles[iso3]["trends"][short_name].append({
                "year": year,
                "value": round(value, 2) if value else None,
                "is_imputed": bool(is_imputed),
            })

    # Set latest values (most recent non-null for each indicator), plus
    # whether that latest point is real or ML-imputed
    for iso3, profile in profiles.items():
        for short_name, trend in profile["trends"].items():
            if trend:
                profile["latest"][short_name] = trend[-1]["value"]
                profile["latest_is_imputed"][short_name] = trend[-1]["is_imputed"]
    
    path = DASHBOARD_DATA_DIR / "country_profiles.json"
    with open(path, "w") as f:
        # No indent: with 60 indicators x 54 countries x 25 years, pretty-printing
        # roughly triples this file's size for a payload nothing renders as text.
        json.dump(profiles, f, separators=(",", ":"))
    logger.info(f"Exported {len(profiles)} country profiles")


def _export_rankings(conn: duckdb.DuckDBPyConnection) -> None:
    """Export country rankings for each indicator (most recent year with data)."""
    rankings: dict[str, list] = {}
    
    for code, meta in INDICATORS.items():
        short = meta["short"]
        rows = conn.execute("""
            WITH latest AS (
                SELECT 
                    dc.iso3_code,
                    dc.country_name,
                    f.value,
                    dd.year,
                    ROW_NUMBER() OVER (PARTITION BY dc.iso3_code ORDER BY dd.year DESC) as rn
                FROM fact_indicators f
                JOIN dim_country dc ON f.country_key = dc.country_key
                JOIN dim_indicator di ON f.indicator_key = di.indicator_key
                JOIN dim_date dd ON f.date_key = dd.date_key
                WHERE di.indicator_code = ? AND f.value IS NOT NULL
            )
            SELECT iso3_code, country_name, value, year
            FROM latest
            WHERE rn = 1
            ORDER BY value DESC
        """, [code]).fetchall()
        
        ranked = []
        for rank, (iso3, name, value, year) in enumerate(rows, 1):
            ranked.append({
                "rank": rank,
                "country": name,
                "iso3": iso3,
                "value": round(value, 2),
                "year": year,
            })
        rankings[short] = ranked
    
    path = DASHBOARD_DATA_DIR / "rankings.json"
    with open(path, "w") as f:
        json.dump(rankings, f, separators=(",", ":"))
    logger.info(f"Exported rankings for {len(rankings)} indicators")


def _export_summary_stats(conn: duckdb.DuckDBPyConnection) -> None:
    """Export aggregate summary statistics."""
    summary = {}
    
    for code, meta in INDICATORS.items():
        short = meta["short"]
        row = conn.execute("""
            WITH latest AS (
                SELECT 
                    f.value,
                    dd.year,
                    ROW_NUMBER() OVER (PARTITION BY dc.iso3_code ORDER BY dd.year DESC) as rn
                FROM fact_indicators f
                JOIN dim_country dc ON f.country_key = dc.country_key
                JOIN dim_indicator di ON f.indicator_key = di.indicator_key
                JOIN dim_date dd ON f.date_key = dd.date_key
                WHERE di.indicator_code = ? AND f.value IS NOT NULL
            )
            SELECT 
                AVG(value) as avg_val,
                MIN(value) as min_val,
                MAX(value) as max_val,
                MEDIAN(value) as median_val,
                COUNT(*) as country_count
            FROM latest WHERE rn = 1
        """, [code]).fetchone()
        
        summary[short] = {
            "name": meta["name"],
            "category": meta["category"],
            "unit": meta["unit"],
            "avg": round(row[0], 2) if row[0] else None,
            "min": round(row[1], 2) if row[1] else None,
            "max": round(row[2], 2) if row[2] else None,
            "median": round(row[3], 2) if row[3] else None,
            "countries": row[4],
        }
    
    # Total Africa GDP
    total_gdp = conn.execute("""
        WITH latest AS (
            SELECT f.value,
                ROW_NUMBER() OVER (PARTITION BY dc.iso3_code ORDER BY dd.year DESC) as rn
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.indicator_code = 'NY.GDP.MKTP.CD' AND f.value IS NOT NULL
        )
        SELECT SUM(value) FROM latest WHERE rn = 1
    """).fetchone()[0]
    
    total_pop = conn.execute("""
        WITH latest AS (
            SELECT f.value,
                ROW_NUMBER() OVER (PARTITION BY dc.iso3_code ORDER BY dd.year DESC) as rn
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.indicator_code = 'SP.POP.TOTL' AND f.value IS NOT NULL
        )
        SELECT SUM(value) FROM latest WHERE rn = 1
    """).fetchone()[0]
    
    summary["_africa_totals"] = {
        "total_gdp": round(total_gdp, 0) if total_gdp else 0,
        "total_population": round(total_pop, 0) if total_pop else 0,
        "countries_tracked": len(AFRICAN_COUNTRIES),
        "indicators_tracked": len(INDICATORS),
    }
    
    path = DASHBOARD_DATA_DIR / "summary_stats.json"
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Exported summary statistics")


def _export_projections(conn: duckdb.DuckDBPyConnection) -> None:
    """Export 5-year forecasts, keyed the same way as country_profiles trends
    (iso3 -> short_name -> [{year, value, ...}]) so the dashboard can append
    a projected segment onto the same trend chart with one lookup."""
    rows = conn.execute("""
        SELECT dc.iso3_code, di.short_name, p.year, p.projected_value, p.method, p.confidence
        FROM projections p
        JOIN dim_country dc ON p.country_key = dc.country_key
        JOIN dim_indicator di ON p.indicator_key = di.indicator_key
        ORDER BY dc.iso3_code, di.short_name, p.year
    """).fetchall()

    by_country: dict[str, dict[str, list[dict]]] = {}
    for iso3, short_name, year, value, method, confidence in rows:
        by_country.setdefault(iso3, {}).setdefault(short_name, []).append({
            "year": year,
            "value": round(value, 2),
            "method": method,
            "confidence": round(confidence, 3) if confidence is not None else None,
        })

    path = DASHBOARD_DATA_DIR / "projections.json"
    with open(path, "w") as f:
        json.dump(by_country, f, separators=(",", ":"))
    logger.info(f"Exported projections for {len(by_country)} countries")
