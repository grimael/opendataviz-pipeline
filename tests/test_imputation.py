"""Tests for the ML imputation module — hermetic, uses a throwaway DuckDB file."""

import duckdb
import pytest

from pipeline.load import create_schema
from pipeline.imputation import DataImputer, MIN_ROWS_FOR_IMPUTATION
from pipeline.config import INDICATORS

ECONOMY_CODES = ["NY.GDP.MKTP.CD", "SP.POP.TOTL", "FP.CPI.TOTL.ZG"]


def _seed_warehouse(db_path: str, n_countries: int, n_years: int) -> None:
    """Build a minimal Economy-pole warehouse with predictable gaps.

    Every (country, year, indicator) cell is populated except FP.CPI.TOTL.ZG
    on country index 0, which is left NULL — that's the gap imputation must fill.
    """
    conn = duckdb.connect(db_path)
    create_schema(conn)

    for i in range(n_countries):
        conn.execute(
            "INSERT INTO dim_country (country_key, iso3_code, iso2_code, country_name, region) VALUES (?, ?, ?, ?, ?)",
            [i + 1, f"C{i:02d}", f"C{i}", f"Country {i}", "Test Region"],
        )
    for i, code in enumerate(ECONOMY_CODES):
        conn.execute(
            "INSERT INTO dim_indicator (indicator_key, indicator_code, indicator_name, category, unit, short_name) VALUES (?, ?, ?, ?, ?, ?)",
            [i + 1, code, code, "Economy", "unit", INDICATORS[code]["short"]],
        )
    years = list(range(2000, 2000 + n_years))
    for y in years:
        conn.execute("INSERT INTO dim_date (date_key, year, decade, is_recent) VALUES (?, ?, ?, ?)", [y, y, "2000s", False])

    for ci in range(n_countries):
        for yi, y in enumerate(years):
            for indi, code in enumerate(ECONOMY_CODES):
                is_gap = code == "FP.CPI.TOTL.ZG" and ci == 0
                value = None if is_gap else float(1000 * (ci + 1) + 10 * yi + indi)
                conn.execute(
                    "INSERT INTO fact_indicators (country_key, indicator_key, date_key, value) VALUES (?, ?, ?, ?)",
                    [ci + 1, indi + 1, y, value],
                )
    conn.close()


@pytest.fixture
def seeded_db(tmp_path):
    db_path = str(tmp_path / "test_warehouse.duckdb")
    _seed_warehouse(db_path, n_countries=6, n_years=10)
    return db_path


def test_impute_indicator_fills_gaps_and_flags_them(seeded_db):
    imputer = DataImputer(db_path=seeded_db)
    result = imputer.impute_indicator("FP.CPI.TOTL.ZG", method="knn")

    assert result.total_missing == 10  # 10 years, all gapped for country 0
    assert result.imputed == 10
    assert result.skipped_reason is None

    conn = duckdb.connect(seeded_db, read_only=True)
    row = conn.execute("""
        SELECT COUNT(*) FROM fact_indicators f
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        JOIN dim_country dc ON f.country_key = dc.country_key
        WHERE di.indicator_code = 'FP.CPI.TOTL.ZG' AND dc.iso3_code = 'C00'
          AND f.value IS NOT NULL AND f.is_imputed AND f.imputation_method = 'knn'
    """).fetchone()
    assert row[0] == 10
    conn.close()


def test_impute_indicator_never_touches_real_values(seeded_db):
    imputer = DataImputer(db_path=seeded_db)
    imputer.impute_indicator("FP.CPI.TOTL.ZG", method="knn")

    conn = duckdb.connect(seeded_db, read_only=True)
    real_untouched = conn.execute("""
        SELECT COUNT(*) FROM fact_indicators f
        JOIN dim_indicator di ON f.indicator_key = di.indicator_key
        WHERE di.indicator_code = 'NY.GDP.MKTP.CD' AND f.is_imputed
    """).fetchone()[0]
    assert real_untouched == 0
    conn.close()


def test_impute_indicator_no_missing_values_is_a_noop(seeded_db):
    imputer = DataImputer(db_path=seeded_db)
    result = imputer.impute_indicator("NY.GDP.MKTP.CD", method="knn")
    assert result.total_missing == 0
    assert result.imputed == 0
    assert result.skipped_reason == "no missing values"


def test_impute_indicator_skips_when_pole_too_small(tmp_path):
    db_path = str(tmp_path / "tiny_warehouse.duckdb")
    _seed_warehouse(db_path, n_countries=2, n_years=2)  # 4 rows < MIN_ROWS_FOR_IMPUTATION
    imputer = DataImputer(db_path=db_path)
    result = imputer.impute_indicator("FP.CPI.TOTL.ZG", method="knn")

    assert result.total_missing == 2
    assert result.imputed == 0
    assert result.skipped_reason == "not enough rows in pole"


def test_run_all_covers_every_configured_indicator(seeded_db, monkeypatch):
    import pipeline.imputation as imputation_module

    monkeypatch.setattr(imputation_module, "INDICATORS", {
        code: {"short": INDICATORS[code]["short"], "category": "Economy"} for code in ECONOMY_CODES
    })
    monkeypatch.setattr(imputation_module, "POLES", ["Economy"])

    results = DataImputer(db_path=seeded_db).run_all(method="knn")
    assert {r.indicator_code for r in results} == set(ECONOMY_CODES)
