"""Tool functions exposed to the conversational agent via LLM function calling.

Each tool wraps the same DuckDB queries as the equivalent REST route (see
api/routes/), so the agent's answers are grounded in exactly the same data a
human would get from /data, /indicators, /projections etc. — never fabricated,
always traceable back to observed / imputed / projected.
"""

import json
import logging
from pathlib import Path

import duckdb

from pipeline.config import DASHBOARD_DATA_DIR, POLES

logger = logging.getLogger(__name__)

HEADLINE_INDICATORS = [
    "gdp", "gdp_growth", "population", "inflation",
    "life_expectancy", "literacy_rate", "internet_users", "electricity_access",
]


def _resolve_indicator(conn: duckdb.DuckDBPyConnection, indicator: str) -> tuple[str, str, str] | None:
    row = conn.execute(
        "SELECT indicator_code, indicator_name, short_name FROM dim_indicator WHERE indicator_code = ? OR short_name = ?",
        [indicator, indicator.lower()],
    ).fetchone()
    return row


def _resolve_country(conn: duckdb.DuckDBPyConnection, country: str) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT iso3_code, country_name FROM dim_country WHERE iso3_code = ? OR lower(country_name) = ?",
        [country.upper(), country.lower()],
    ).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT iso3_code, country_name FROM dim_country WHERE lower(country_name) LIKE ?",
        [f"%{country.lower()}%"],
    ).fetchone()
    return row


def list_indicators(conn: duckdb.DuckDBPyConnection, pole: str | None = None) -> dict:
    if pole and pole not in POLES:
        return {"error": f"Pôle inconnu {pole!r}. Attendu : {POLES}"}
    query = "SELECT indicator_code, indicator_name, short_name, category, unit FROM dim_indicator"
    params: list = []
    if pole:
        query += " WHERE category = ?"
        params.append(pole)
    query += " ORDER BY category, indicator_name"
    rows = conn.execute(query, params).fetchall()
    return {
        "indicators": [
            {"code": r[0], "name": r[1], "short_name": r[2], "pole": r[3], "unit": r[4]} for r in rows
        ]
    }


def list_countries(conn: duckdb.DuckDBPyConnection, region: str | None = None) -> dict:
    query = "SELECT iso3_code, country_name, region, income_level FROM dim_country"
    params: list = []
    if region:
        query += " WHERE region = ?"
        params.append(region)
    query += " ORDER BY country_name"
    rows = conn.execute(query, params).fetchall()
    return {"countries": [{"iso3": r[0], "name": r[1], "region": r[2], "income_level": r[3]} for r in rows]}


def get_indicator_timeseries(
    conn: duckdb.DuckDBPyConnection,
    indicator: str,
    countries: list[str],
    year_from: int | None = None,
    year_to: int | None = None,
    include_imputed: bool = True,
) -> dict:
    ind = _resolve_indicator(conn, indicator)
    if not ind:
        return {"error": f"Indicateur inconnu : {indicator!r}"}
    code, name, short = ind

    if not countries:
        return {"error": "Précise au moins un pays (nom ou code ISO3)."}
    resolved = []
    for c in countries[:6]:
        row = _resolve_country(conn, c)
        if row:
            resolved.append(row)
    if not resolved:
        return {"error": f"Aucun des pays {countries!r} n'a été reconnu."}

    iso3s = [r[0] for r in resolved]
    placeholders = ",".join("?" for _ in iso3s)
    query = f"""
        SELECT dc.iso3_code, dc.country_name, dd.year, f.value, f.is_imputed
        FROM fact_indicators f
        JOIN dim_country dc ON f.country_key = dc.country_key
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        JOIN dim_date dd ON f.date_key = dd.date_key
        WHERE di.indicator_code = ? AND dc.iso3_code IN ({placeholders})
    """
    params: list = [code, *iso3s]
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
    series: dict[str, list[dict]] = {}
    for iso3, cname, year, value, is_imputed in rows:
        series.setdefault(f"{cname} ({iso3})", []).append(
            {"year": year, "value": value, "nature": "imputée" if is_imputed else "observée"}
        )
    return {"indicator": {"code": code, "name": name, "short_name": short}, "series": series}


def get_indicator_ranking(
    conn: duckdb.DuckDBPyConnection,
    indicator: str,
    top_n: int = 10,
    order: str = "desc",
    year: int | None = None,
) -> dict:
    ind = _resolve_indicator(conn, indicator)
    if not ind:
        return {"error": f"Indicateur inconnu : {indicator!r}"}
    code, name, short = ind
    order_sql = "DESC" if order.lower() != "asc" else "ASC"

    if year is not None:
        query = f"""
            SELECT dc.country_name, dc.iso3_code, f.value, f.is_imputed
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.indicator_code = ? AND dd.year = ? AND f.value IS NOT NULL
            ORDER BY f.value {order_sql}
            LIMIT ?
        """
        rows = conn.execute(query, [code, year, min(top_n, 54)]).fetchall()
        ranking = [{"country": r[0], "iso3": r[1], "value": r[2], "year": year, "nature": "imputée" if r[3] else "observée"} for r in rows]
    else:
        # Most recent available year per country (mirrors dashboard "latest" semantics).
        query = f"""
            WITH latest AS (
                SELECT dc.country_name, dc.iso3_code, f.value, f.is_imputed, dd.year,
                       ROW_NUMBER() OVER (PARTITION BY dc.iso3_code ORDER BY dd.year DESC) AS rn
                FROM fact_indicators f
                JOIN dim_country dc ON f.country_key = dc.country_key
                JOIN dim_indicator di ON f.indicator_key = di.indicator_key
                JOIN dim_date dd ON f.date_key = dd.date_key
                WHERE di.indicator_code = ? AND f.value IS NOT NULL
            )
            SELECT country_name, iso3_code, value, is_imputed, year FROM latest
            WHERE rn = 1
            ORDER BY value {order_sql}
            LIMIT ?
        """
        rows = conn.execute(query, [code, min(top_n, 54)]).fetchall()
        ranking = [{"country": r[0], "iso3": r[1], "value": r[2], "year": r[4], "nature": "imputée" if r[3] else "observée"} for r in rows]

    return {"indicator": {"code": code, "name": name, "short_name": short}, "ranking": ranking}


def get_projections(conn: duckdb.DuckDBPyConnection, indicator: str, countries: list[str]) -> dict:
    ind = _resolve_indicator(conn, indicator)
    if not ind:
        return {"error": f"Indicateur inconnu : {indicator!r}"}
    code, name, short = ind

    resolved = [r for c in countries[:6] if (r := _resolve_country(conn, c))]
    if not resolved:
        return {"error": f"Aucun des pays {countries!r} n'a été reconnu."}
    iso3s = [r[0] for r in resolved]
    placeholders = ",".join("?" for _ in iso3s)

    query = f"""
        SELECT dc.iso3_code, dc.country_name, p.year, p.projected_value, p.method, p.confidence
        FROM projections p
        JOIN dim_country dc ON p.country_key = dc.country_key
        JOIN dim_indicator di ON p.indicator_key = di.indicator_key
        WHERE di.indicator_code = ? AND dc.iso3_code IN ({placeholders})
        ORDER BY dc.country_name, p.year
    """
    rows = conn.execute(query, [code, *iso3s]).fetchall()
    if not rows:
        return {"indicator": {"code": code, "name": name}, "projections": {}, "note": "Aucune projection disponible (série trop courte ou pays non couvert)."}

    projections: dict[str, list[dict]] = {}
    for iso3, cname, year, value, method, confidence in rows:
        projections.setdefault(f"{cname} ({iso3})", []).append(
            {"year": year, "value": value, "method": method, "confidence_r2": confidence}
        )
    return {"indicator": {"code": code, "name": name, "short_name": short}, "projections": projections}


def get_country_profile(conn: duckdb.DuckDBPyConnection, country: str) -> dict:
    row = _resolve_country(conn, country)
    if not row:
        return {"error": f"Pays inconnu : {country!r}"}
    iso3, name = row

    meta = conn.execute(
        "SELECT region, income_level, capital_city, latitude, longitude FROM dim_country WHERE iso3_code = ?",
        [iso3],
    ).fetchone()

    placeholders = ",".join("?" for _ in HEADLINE_INDICATORS)
    query = f"""
        WITH latest AS (
            SELECT di.short_name, di.indicator_name, f.value, f.is_imputed, dd.year,
                   ROW_NUMBER() OVER (PARTITION BY di.short_name ORDER BY dd.year DESC) AS rn
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE dc.iso3_code = ? AND di.short_name IN ({placeholders}) AND f.value IS NOT NULL
        )
        SELECT short_name, indicator_name, value, is_imputed, year FROM latest WHERE rn = 1
    """
    rows = conn.execute(query, [iso3, *HEADLINE_INDICATORS]).fetchall()
    indicators = {r[0]: {"name": r[1], "value": r[2], "year": r[4], "nature": "imputée" if r[3] else "observée"} for r in rows}

    return {
        "iso3": iso3,
        "name": name,
        "region": meta[0] if meta else None,
        "income_level": meta[1] if meta else None,
        "capital_city": meta[2] if meta else None,
        "headline_indicators": indicators,
    }


def compare_countries(conn: duckdb.DuckDBPyConnection, indicator: str, countries: list[str], year: int | None = None) -> dict:
    ind = _resolve_indicator(conn, indicator)
    if not ind:
        return {"error": f"Indicateur inconnu : {indicator!r}"}
    code, name, short = ind

    resolved = [r for c in countries[:8] if (r := _resolve_country(conn, c))]
    if len(resolved) < 2:
        return {"error": "Précise au moins deux pays reconnus pour une comparaison."}
    iso3s = [r[0] for r in resolved]
    placeholders = ",".join("?" for _ in iso3s)

    if year is not None:
        query = f"""
            SELECT dc.country_name, dc.iso3_code, f.value, f.is_imputed, dd.year
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.indicator_code = ? AND dc.iso3_code IN ({placeholders}) AND dd.year = ?
            ORDER BY f.value DESC
        """
        rows = conn.execute(query, [code, *iso3s, year]).fetchall()
    else:
        query = f"""
            WITH latest AS (
                SELECT dc.country_name, dc.iso3_code, f.value, f.is_imputed, dd.year,
                       ROW_NUMBER() OVER (PARTITION BY dc.iso3_code ORDER BY dd.year DESC) AS rn
                FROM fact_indicators f
                JOIN dim_country dc ON f.country_key = dc.country_key
                JOIN dim_indicator di ON f.indicator_key = di.indicator_key
                JOIN dim_date dd ON f.date_key = dd.date_key
                WHERE di.indicator_code = ? AND dc.iso3_code IN ({placeholders}) AND f.value IS NOT NULL
            )
            SELECT country_name, iso3_code, value, is_imputed, year FROM latest WHERE rn = 1
            ORDER BY value DESC
        """
        rows = conn.execute(query, [code, *iso3s]).fetchall()

    comparison = [{"country": r[0], "iso3": r[1], "value": r[2], "year": r[4], "nature": "imputée" if r[3] else "observée"} for r in rows]
    return {"indicator": {"code": code, "name": name, "short_name": short}, "comparison": comparison}


def get_data_quality(conn: duckdb.DuckDBPyConnection) -> dict:
    path = Path(DASHBOARD_DATA_DIR) / "quality_report.json"
    if not path.exists():
        return {"error": "Rapport qualité indisponible."}
    report = json.loads(path.read_text())
    dims = report.get("dimensions", {})
    return {
        "overall_score": report.get("overall_score"),
        "last_run": report.get("last_run"),
        "completeness_score": dims.get("completeness", {}).get("score"),
        "validity_score": dims.get("validity", {}).get("score"),
        "freshness_score": dims.get("freshness", {}).get("score"),
        "imputation": report.get("imputation"),
    }


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_indicators",
            "description": "Liste les indicateurs disponibles (60 au total), optionnellement filtrés par pôle (Economy, Health, Education, Infrastructure).",
            "parameters": {
                "type": "object",
                "properties": {"pole": {"type": "string", "description": "Economy, Health, Education ou Infrastructure"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_countries",
            "description": "Liste les 54 pays africains couverts, optionnellement filtrés par région.",
            "parameters": {
                "type": "object",
                "properties": {"region": {"type": "string", "description": "ex: 'West Africa', 'East Africa'"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_indicator_timeseries",
            "description": "Série temporelle année par année d'un indicateur pour un ou plusieurs pays précis (max 6). À utiliser quand l'utilisateur demande une évolution ou des chiffres détaillés par année.",
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string", "description": "Code World Bank (ex: NY.GDP.MKTP.CD) ou nom court (ex: gdp)"},
                    "countries": {"type": "array", "items": {"type": "string"}, "description": "Noms ou codes ISO3 des pays, ex: ['Nigeria', 'KEN']"},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "include_imputed": {"type": "boolean", "description": "false pour n'avoir que les valeurs réellement observées"},
                },
                "required": ["indicator", "countries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_indicator_ranking",
            "description": "Classement des pays africains sur un indicateur (top ou bottom N), pour la dernière année disponible ou une année précise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string"},
                    "top_n": {"type": "integer", "description": "Nombre de pays à retourner (max 54), défaut 10"},
                    "order": {"type": "string", "enum": ["desc", "asc"], "description": "desc = plus élevé d'abord"},
                    "year": {"type": "integer", "description": "Année précise ; sinon la dernière disponible par pays"},
                },
                "required": ["indicator"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_projections",
            "description": "Projections 2025-2029 (ElasticNet) d'un indicateur pour un ou plusieurs pays, avec indice de confiance R².",
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string"},
                    "countries": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["indicator", "countries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_country_profile",
            "description": "Fiche pays : région, niveau de revenu, capitale, et les indicateurs phares (PIB, croissance, population, inflation, espérance de vie, alphabétisation, internet, électricité).",
            "parameters": {
                "type": "object",
                "properties": {"country": {"type": "string", "description": "Nom ou code ISO3 du pays"}},
                "required": ["country"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_countries",
            "description": "Compare plusieurs pays (2 à 8) sur un même indicateur, pour la dernière année disponible ou une année précise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string"},
                    "countries": {"type": "array", "items": {"type": "string"}},
                    "year": {"type": "integer"},
                },
                "required": ["indicator", "countries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_quality",
            "description": "Score de qualité global des données OpenDataViz (complétude, validité, fraîcheur) et statistiques d'imputation ML.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_DISPATCH = {
    "list_indicators": list_indicators,
    "list_countries": list_countries,
    "get_indicator_timeseries": get_indicator_timeseries,
    "get_indicator_ranking": get_indicator_ranking,
    "get_projections": get_projections,
    "get_country_profile": get_country_profile,
    "compare_countries": compare_countries,
    "get_data_quality": get_data_quality,
}


def execute_tool(name: str, args: dict, conn: duckdb.DuckDBPyConnection) -> dict:
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"Outil inconnu : {name!r}"}
    try:
        return fn(conn, **args)
    except Exception:
        logger.exception("Tool %r failed with args %r", name, args)
        return {"error": f"Échec de l'outil {name!r} : erreur interne."}
