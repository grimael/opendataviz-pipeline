"""Tests for the FastAPI service.

Requires fastapi/pydantic, whose compiled pydantic_core extension is blocked
by Smart App Control on this dev machine (see api/Dockerfile — the API is
validated by running it in Docker instead). `importorskip` makes this file a
clean skip on a host where fastapi can't be imported, rather than an error
that would take the rest of the suite down with it.
"""

import duckdb
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from pipeline.load import create_schema
from pipeline.config import INDICATORS

GDP_CODE = "NY.GDP.MKTP.CD"
POP_CODE = "SP.POP.TOTL"


def _seed(db_path: str) -> None:
    conn = duckdb.connect(db_path)
    create_schema(conn)

    countries = [(1, "KEN", "KE", "Kenya", "East Africa"), (2, "NGA", "NG", "Nigeria", "West Africa")]
    for row in countries:
        conn.execute(
            "INSERT INTO dim_country (country_key, iso3_code, iso2_code, country_name, region) VALUES (?, ?, ?, ?, ?)",
            list(row),
        )

    indicators = [(1, GDP_CODE, "Economy"), (2, POP_CODE, "Economy")]
    for key, code, category in indicators:
        conn.execute(
            "INSERT INTO dim_indicator (indicator_key, indicator_code, indicator_name, category, unit, short_name) VALUES (?, ?, ?, ?, ?, ?)",
            [key, code, code, category, "unit", INDICATORS[code]["short"]],
        )

    for year in (2022, 2023):
        conn.execute("INSERT INTO dim_date (date_key, year, decade, is_recent) VALUES (?, ?, ?, ?)", [year, year, "2020s", True])

    for country_key in (1, 2):
        for indicator_key in (1, 2):
            for year in (2022, 2023):
                conn.execute(
                    "INSERT INTO fact_indicators (country_key, indicator_key, date_key, value) VALUES (?, ?, ?, ?)",
                    [country_key, indicator_key, year, float(country_key * 1000 + indicator_key * 100 + year)],
                )

    conn.execute(
        "INSERT INTO projections (country_key, indicator_key, year, projected_value, method, confidence) VALUES (?, ?, ?, ?, ?, ?)",
        [1, 1, 2024, 999.0, "elasticnet", 0.9],
    )

    # One GDP row flagged imputed, so scope=observed vs scope=all differ.
    conn.execute(
        "UPDATE fact_indicators SET is_imputed = TRUE, imputation_method = 'knn' WHERE country_key = 1 AND indicator_key = 1 AND date_key = 2023"
    )
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "api_test.duckdb")
    _seed(db_path)

    import api.db as api_db
    from api.main import app

    def override_get_connection():
        conn = duckdb.connect(db_path, read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[api_db.get_connection] = override_get_connection
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_facts"] == 8  # 2 countries x 2 indicators x 2 years
    assert body["total_projections"] == 1


def test_countries(client):
    r = client.get("/countries")
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert names == {"Kenya", "Nigeria"}


def test_indicators_grouped_by_pole(client):
    r = client.get("/indicators")
    assert r.status_code == 200
    assert len(r.json()["Economy"]) == 2


def test_indicators_invalid_pole_is_400(client):
    r = client.get("/indicators", params={"pole": "NotAPole"})
    assert r.status_code == 400


def test_data_resolves_short_name_and_wb_code_identically(client):
    a = client.get(f"/data/{INDICATORS[GDP_CODE]['short']}").json()
    b = client.get(f"/data/{GDP_CODE}").json()
    assert a == b
    assert len(a) == 4  # 2 countries x 2 years


def test_data_country_filter(client):
    r = client.get(f"/data/{GDP_CODE}", params={"country": "KEN"})
    assert all(row["country_iso3"] == "KEN" for row in r.json())


def test_data_unknown_indicator_is_404(client):
    r = client.get("/data/not_a_real_indicator")
    assert r.status_code == 404


def test_projections_endpoint(client):
    r = client.get(f"/projections/{GDP_CODE}")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["method"] == "elasticnet"


def test_export_csv(client):
    r = client.get(f"/export/{GDP_CODE}", params={"format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("iso3,country,year")


def test_export_parquet(client):
    r = client.get(f"/export/{GDP_CODE}", params={"format": "parquet"})
    assert r.status_code == 200
    assert r.content[:4] == b"PAR1"


def test_export_xlsx(client):
    r = client.get(f"/export/{GDP_CODE}", params={"format": "xlsx"})
    assert r.status_code == 200
    assert r.content[:4] == b"PK\x03\x04"  # xlsx is a zip archive


def test_export_stata(client):
    r = client.get(f"/export/{GDP_CODE}", params={"format": "dta"})
    assert r.status_code == 200
    assert r.content[:11] == b"<stata_dta>"


def test_export_spss(client):
    r = client.get(f"/export/{GDP_CODE}", params={"format": "sav"})
    assert r.status_code == 200
    assert r.content[:4] == b"$FL2"


def test_export_scope_observed_excludes_imputed(client):
    all_rows = client.get(f"/export/{GDP_CODE}", params={"format": "csv", "scope": "all"}).text.strip().splitlines()
    observed_rows = client.get(f"/export/{GDP_CODE}", params={"format": "csv", "scope": "observed"}).text.strip().splitlines()
    # Fixture flags exactly one of the 4 GDP rows as imputed.
    assert len(all_rows) == 5  # header + 4 data rows
    assert len(observed_rows) == 4  # header + 3 data rows
    assert "True" not in "\n".join(observed_rows)


def test_export_invalid_format_is_422(client):
    r = client.get(f"/export/{GDP_CODE}", params={"format": "xml"})
    assert r.status_code == 422


def test_export_invalid_scope_is_422(client):
    r = client.get(f"/export/{GDP_CODE}", params={"scope": "bogus"})
    assert r.status_code == 422
