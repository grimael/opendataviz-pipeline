"""Transform raw World Bank records into dimensional model structures."""

import logging
from typing import Any
from .config import INDICATORS, AFRICAN_COUNTRIES

logger = logging.getLogger(__name__)


def transform_records(raw_records: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """Transform raw API records into star-schema-ready structures.
    
    Returns dict with keys: facts, dim_country, dim_indicator, dim_date
    """
    facts = []
    years_seen: set[int] = set()
    countries_seen: set[str] = set()
    
    # Build country key mapping (deterministic)
    country_keys = {iso3: idx + 1 for idx, iso3 in enumerate(sorted(AFRICAN_COUNTRIES.keys()))}
    indicator_keys = {code: idx + 1 for idx, code in enumerate(sorted(INDICATORS.keys()))}
    
    for record in raw_records:
        country_id = record.get("countryiso3code") or record.get("country", {}).get("id", "")
        indicator_code = record.get("indicator", {}).get("id", "")
        year_str = record.get("date", "")
        value = record.get("value")
        
        # Skip if not an African country we track or unknown indicator
        if country_id not in AFRICAN_COUNTRIES or indicator_code not in INDICATORS:
            continue
        
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            continue
        
        years_seen.add(year)
        countries_seen.add(country_id)
        
        facts.append({
            "country_key": country_keys[country_id],
            "indicator_key": indicator_keys[indicator_code],
            "date_key": year,
            "country_iso3": country_id,
            "indicator_code": indicator_code,
            "value": float(value) if value is not None else None,
        })
    
    # Calculate year-over-year change
    facts = _add_yoy_change(facts)
    
    # Build dimensions
    dim_country = _build_dim_country(country_keys)
    dim_indicator = _build_dim_indicator(indicator_keys)
    dim_date = _build_dim_date(years_seen)
    
    logger.info(f"Transformed: {len(facts)} facts, {len(dim_country)} countries, "
                f"{len(dim_indicator)} indicators, {len(dim_date)} years")
    
    return {
        "facts": facts,
        "dim_country": dim_country,
        "dim_indicator": dim_indicator,
        "dim_date": dim_date,
    }


def _add_yoy_change(facts: list[dict]) -> list[dict]:
    """Calculate year-over-year change for each country+indicator pair."""
    # Group by country+indicator
    grouped: dict[tuple, dict[int, float | None]] = {}
    for f in facts:
        key = (f["country_iso3"], f["indicator_code"])
        if key not in grouped:
            grouped[key] = {}
        grouped[key][f["date_key"]] = f["value"]
    
    # Calculate YoY
    for f in facts:
        key = (f["country_iso3"], f["indicator_code"])
        year = f["date_key"]
        current = f["value"]
        previous = grouped[key].get(year - 1)
        
        if current is not None and previous is not None and previous != 0:
            f["yoy_change"] = round(((current - previous) / abs(previous)) * 100, 2)
        else:
            f["yoy_change"] = None
    
    return facts


def _build_dim_country(country_keys: dict[str, int]) -> list[dict]:
    """Build country dimension table."""
    rows = []
    for iso3, info in AFRICAN_COUNTRIES.items():
        rows.append({
            "country_key": country_keys[iso3],
            "iso3_code": iso3,
            "iso2_code": info["iso2"],
            "country_name": info["name"],
            "region": info["region"],
        })
    return rows


def _build_dim_indicator(indicator_keys: dict[str, int]) -> list[dict]:
    """Build indicator dimension table."""
    rows = []
    for code, meta in INDICATORS.items():
        rows.append({
            "indicator_key": indicator_keys[code],
            "indicator_code": code,
            "indicator_name": meta["name"],
            "category": meta["category"],
            "unit": meta["unit"],
            "short_name": meta["short"],
        })
    return rows


def _build_dim_date(years: set[int]) -> list[dict]:
    """Build date dimension table."""
    rows = []
    for year in sorted(years):
        decade = f"{(year // 10) * 10}s"
        rows.append({
            "date_key": year,
            "year": year,
            "decade": decade,
            "is_recent": year >= 2020,
        })
    return rows
