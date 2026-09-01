"""Tests for the OpenDataViz Pipeline."""

import json
import os
from pathlib import Path

# Skip tests that need network/DB if not available
import pytest


def test_config_has_all_countries():
    """Verify we have 54 African countries configured."""
    from pipeline.config import AFRICAN_COUNTRIES
    assert len(AFRICAN_COUNTRIES) == 54


def test_config_has_60_indicators():
    """Verify we have 60 indicators configured, 15 per pole."""
    from pipeline.config import INDICATORS, POLES
    from collections import Counter
    assert len(INDICATORS) == 60
    by_pole = Counter(v["category"] for v in INDICATORS.values())
    assert set(by_pole) == set(POLES)
    assert all(count == 15 for count in by_pole.values())


def test_config_dq_thresholds_cover_all_indicators():
    """Every indicator must have a validity threshold for quality checks."""
    from pipeline.config import INDICATORS, DQ_THRESHOLDS
    assert set(INDICATORS.keys()) == set(DQ_THRESHOLDS.keys())


def test_config_short_names_unique():
    """Each indicator has a unique short name."""
    from pipeline.config import INDICATORS
    shorts = [v["short"] for v in INDICATORS.values()]
    assert len(shorts) == len(set(shorts))


def test_transform_empty_input():
    """Transform handles empty input gracefully."""
    from pipeline.transform import transform_records
    result = transform_records([])
    assert result["facts"] == []
    assert len(result["dim_country"]) == 54
    assert len(result["dim_indicator"]) == 60


def test_transform_sample_record():
    """Transform correctly processes a single record."""
    from pipeline.transform import transform_records
    raw = [{
        "countryiso3code": "KEN",
        "indicator": {"id": "SP.POP.TOTL"},
        "country": {"id": "KEN", "value": "Kenya"},
        "date": "2023",
        "value": 56000000,
    }]
    result = transform_records(raw)
    facts = [f for f in result["facts"] if f["country_iso3"] == "KEN" and f["indicator_code"] == "SP.POP.TOTL"]
    assert len(facts) == 1
    assert facts[0]["value"] == 56000000.0
    assert facts[0]["date_key"] == 2023


def test_transform_null_value():
    """Transform preserves null values."""
    from pipeline.transform import transform_records
    raw = [{
        "countryiso3code": "NGA",
        "indicator": {"id": "SE.ADT.LITR.ZS"},
        "country": {"id": "NGA"},
        "date": "2020",
        "value": None,
    }]
    result = transform_records(raw)
    facts = [f for f in result["facts"] if f["country_iso3"] == "NGA"]
    assert len(facts) == 1
    assert facts[0]["value"] is None


def test_dashboard_data_exists():
    """Verify dashboard JSON files are present after running pipeline."""
    data_dir = Path(__file__).parent.parent / "dashboard" / "public" / "data"
    if not data_dir.exists():
        pytest.skip("Dashboard data not generated yet")
    
    for fname in ["country_profiles.json", "rankings.json", "summary_stats.json", "quality_report.json", "indicators.json", "projections.json"]:
        fpath = data_dir / fname
        assert fpath.exists(), f"Missing {fname}"
        data = json.loads(fpath.read_text())
        assert data, f"{fname} is empty"


def test_country_profiles_structure():
    """Verify country profiles have expected structure."""
    data_dir = Path(__file__).parent.parent / "dashboard" / "public" / "data"
    fpath = data_dir / "country_profiles.json"
    if not fpath.exists():
        pytest.skip("country_profiles.json not generated yet")
    
    profiles = json.loads(fpath.read_text())
    assert "KEN" in profiles
    kenya = profiles["KEN"]
    assert kenya["name"] == "Kenya"
    assert "latest" in kenya
    assert "trends" in kenya
    assert "gdp" in kenya["latest"] or "population" in kenya["latest"]
