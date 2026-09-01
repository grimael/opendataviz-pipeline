"""Tests for the projection module — hermetic, uses a throwaway DuckDB file."""

import duckdb
import pytest

from pipeline.load import create_schema
from pipeline.projection import Projector, MIN_HISTORY_YEARS
from pipeline.config import INDICATORS

INDICATOR_CODE = "NY.GDP.MKTP.CD"  # linear-ish, unbounded in DQ_THRESHOLDS -> no clipping surprises


def _seed_warehouse(db_path: str, n_countries: int, n_years: int, with_trend: bool = True) -> None:
    conn = duckdb.connect(db_path)
    create_schema(conn)

    for i in range(n_countries):
        conn.execute(
            "INSERT INTO dim_country (country_key, iso3_code, iso2_code, country_name, region) VALUES (?, ?, ?, ?, ?)",
            [i + 1, f"C{i:02d}", f"C{i}", f"Country {i}", "Test Region"],
        )
    conn.execute(
        "INSERT INTO dim_indicator (indicator_key, indicator_code, indicator_name, category, unit, short_name) VALUES (?, ?, ?, ?, ?, ?)",
        [1, INDICATOR_CODE, INDICATOR_CODE, "Economy", "US$", INDICATORS[INDICATOR_CODE]["short"]],
    )
    years = list(range(2000, 2000 + n_years))
    for y in years:
        conn.execute("INSERT INTO dim_date (date_key, year, decade, is_recent) VALUES (?, ?, ?, ?)", [y, y, "2000s", False])

    for ci in range(n_countries):
        for yi, y in enumerate(years):
            base = 1_000_000_000.0 * (ci + 1)
            value = base + (yi * 50_000_000.0 if with_trend else 0.0)
            conn.execute(
                "INSERT INTO fact_indicators (country_key, indicator_key, date_key, value) VALUES (?, ?, ?, ?)",
                [ci + 1, 1, y, value],
            )
    conn.close()


@pytest.fixture
def seeded_db(tmp_path):
    db_path = str(tmp_path / "test_warehouse.duckdb")
    _seed_warehouse(db_path, n_countries=3, n_years=15)
    return db_path


def test_project_indicator_writes_horizon_years_per_country(seeded_db):
    projector = Projector(db_path=seeded_db, horizon=5)
    result = projector.project_indicator(INDICATOR_CODE, method="elasticnet")

    assert result.countries_projected == 3
    assert result.countries_skipped == 0

    conn = duckdb.connect(seeded_db, read_only=True)
    rows = conn.execute("SELECT year, projected_value, method, confidence FROM projections ORDER BY country_key, year").fetchall()
    conn.close()

    assert len(rows) == 15  # 3 countries x 5 years
    years = {r[0] for r in rows}
    assert years == set(range(2015, 2020))  # last real year is 2014 -> next 5
    assert all(r[2] == "elasticnet" for r in rows)
    assert all(r[3] is not None for r in rows)  # in-sample R^2 recorded


def test_project_indicator_follows_upward_trend(seeded_db):
    Projector(db_path=seeded_db, horizon=5).project_indicator(INDICATOR_CODE)
    conn = duckdb.connect(seeded_db, read_only=True)
    row = conn.execute("""
        SELECT projected_value FROM projections
        WHERE country_key = 1 ORDER BY year LIMIT 1
    """).fetchone()
    conn.close()
    # last observed value for country 1 was 1e9 + 14*5e7 = 1.7e9; a continuing
    # upward trend should project noticeably above that, not below it.
    assert row[0] > 1_000_000_000.0


def test_project_indicator_skips_short_history(tmp_path):
    db_path = str(tmp_path / "short_warehouse.duckdb")
    _seed_warehouse(db_path, n_countries=2, n_years=MIN_HISTORY_YEARS - 1)
    result = Projector(db_path=db_path).project_indicator(INDICATOR_CODE)
    assert result.countries_projected == 0
    assert result.countries_skipped == 2


def test_project_indicator_overwrites_previous_run(seeded_db):
    projector = Projector(db_path=seeded_db, horizon=5)
    projector.project_indicator(INDICATOR_CODE)
    projector.project_indicator(INDICATOR_CODE)  # run twice

    conn = duckdb.connect(seeded_db, read_only=True)
    count = conn.execute("SELECT COUNT(*) FROM projections").fetchone()[0]
    conn.close()
    assert count == 15  # not duplicated
