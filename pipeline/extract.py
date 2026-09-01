"""Extract economic data from the World Bank API v2."""

import httpx
import time
import logging
from typing import Any

from .config import (
    WB_BASE_URL, WB_FORMAT, WB_DATE_RANGE, WB_PER_PAGE,
    INDICATORS, AFRICAN_COUNTRIES,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 2  # seconds


def _build_url(indicator_code: str) -> str:
    """Build World Bank API URL for all African countries and one indicator."""
    country_codes = ";".join(AFRICAN_COUNTRIES.keys())
    return (
        f"{WB_BASE_URL}/country/{country_codes}/indicator/{indicator_code}"
        f"?format={WB_FORMAT}&date={WB_DATE_RANGE}&per_page={WB_PER_PAGE}"
    )


def _fetch_with_retry(client: httpx.Client, url: str) -> list[dict[str, Any]]:
    """Fetch a URL with exponential backoff retries."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            # World Bank returns [metadata, records] for valid queries
            if isinstance(data, list) and len(data) == 2:
                return data[1] or []
            # Sometimes returns a dict with an error message
            logger.warning(f"Unexpected response format: {str(data)[:200]}")
            return []
        except (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectError) as e:
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    logger.error(f"All {MAX_RETRIES} attempts failed for {url[:100]}")
    return []


def extract_all() -> list[dict[str, Any]]:
    """Extract all indicators for all African countries.
    
    Returns a list of raw records from the World Bank API.
    Each record has: country.id, country.value, indicator.id, indicator.value, date, value, etc.
    """
    all_records: list[dict[str, Any]] = []
    
    with httpx.Client() as client:
        for code, meta in INDICATORS.items():
            url = _build_url(code)
            logger.info(f"Extracting {meta['name']} ({code})...")
            records = _fetch_with_retry(client, url)
            count = len(records)
            non_null = sum(1 for r in records if r.get("value") is not None)
            logger.info(f"  → {count} records ({non_null} non-null)")
            all_records.extend(records)
            time.sleep(0.5)  # Be respectful to the free API
    
    logger.info(f"Total extracted: {len(all_records)} records")
    return all_records


def extract_country_metadata(client: httpx.Client | None = None) -> dict[str, dict]:
    """Fetch country metadata (income level, lat/lng, capital) from World Bank."""
    own_client = client is None
    if own_client:
        client = httpx.Client()
    
    try:
        country_codes = ";".join(AFRICAN_COUNTRIES.keys())
        url = f"{WB_BASE_URL}/country/{country_codes}?format={WB_FORMAT}&per_page=100"
        records = _fetch_with_retry(client, url)
        
        metadata = {}
        for r in records:
            iso3 = r.get("id", "")
            if iso3 in AFRICAN_COUNTRIES:
                metadata[iso3] = {
                    "income_level": r.get("incomeLevel", {}).get("value", "Unknown"),
                    "capital_city": r.get("capitalCity", ""),
                    "latitude": float(r.get("latitude", 0) or 0),
                    "longitude": float(r.get("longitude", 0) or 0),
                }
        return metadata
    finally:
        if own_client:
            client.close()
