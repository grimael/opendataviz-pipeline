"""Multi-year forecasting for indicator trends — pipeline/projection.py.

Baseline model: one ElasticNet regression per (country, indicator) pair,
fit on (year -> value) with a light polynomial trend, forecasting `horizon`
years past the latest year in dim_date. Deliberately simple: it's a
regularized linear trend, not a time-series model with seasonality/momentum.

The architecture (one row per country/indicator/year in `projections`, each
tagged with its `method`) is designed so a more sophisticated model can be
swapped in later without touching storage or the API — just add a new
`method` branch in `_fit_and_predict`. Projected values are clipped to the
same DQ_THRESHOLDS ranges used for validity checks, so a runaway extrapolation
(e.g. a percentage indicator drifting past 100%) can't leak into the API.
"""

import logging
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.metrics import r2_score
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from .config import DB_PATH, DQ_THRESHOLDS, INDICATORS
from .load import create_schema

logger = logging.getLogger(__name__)

PROJECTION_HORIZON = 5
MIN_HISTORY_YEARS = 8  # below this, a fitted trend is more noise than signal


@dataclass
class ProjectionResult:
    indicator_code: str
    short_name: str
    countries_projected: int
    countries_skipped: int
    method: str


class Projector:
    """Forecasts `horizon` years ahead per (country, indicator) with ElasticNet."""

    def __init__(self, db_path: str = str(DB_PATH), horizon: int = PROJECTION_HORIZON):
        self.db_path = db_path
        self.horizon = horizon

    def _connect(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect(self.db_path)
        create_schema(conn)  # idempotent: ensures the projections table/columns exist
        return conn

    def _country_series(self, conn: duckdb.DuckDBPyConnection, indicator_code: str) -> pd.DataFrame:
        return conn.execute(
            """
            SELECT dc.iso3_code, dc.country_key, dd.year, f.value
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.indicator_code = ? AND f.value IS NOT NULL
            ORDER BY dc.iso3_code, dd.year
            """,
            [indicator_code],
        ).fetchdf()

    def _fit_and_predict(self, years: np.ndarray, values: np.ndarray, future_years: np.ndarray, method: str):
        """Returns (predictions, in_sample_r2). `method` is the only extension
        point needed to plug in a different model later."""
        if method != "elasticnet":
            raise ValueError(f"Unknown projection method: {method!r}")

        poly = PolynomialFeatures(degree=2, include_bias=False)
        X = poly.fit_transform(years.reshape(-1, 1))
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)

        model = ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=42, max_iter=5000)
        model.fit(Xs, values)

        in_sample_r2 = r2_score(values, model.predict(Xs)) if len(values) > 2 else None

        Xf = scaler.transform(poly.transform(future_years.reshape(-1, 1)))
        return model.predict(Xf), in_sample_r2

    def project_indicator(self, indicator_code: str, method: str = "elasticnet") -> ProjectionResult:
        meta = INDICATORS[indicator_code]
        short = meta["short"]
        thresh = DQ_THRESHOLDS.get(indicator_code)

        conn = self._connect()
        try:
            indicator_key = conn.execute(
                "SELECT indicator_key FROM dim_indicator WHERE indicator_code = ?", [indicator_code]
            ).fetchone()[0]
            last_year = conn.execute("SELECT MAX(year) FROM dim_date").fetchone()[0]
            future_years = np.arange(last_year + 1, last_year + 1 + self.horizon)

            data = self._country_series(conn, indicator_code)
            conn.execute("DELETE FROM projections WHERE indicator_key = ?", [indicator_key])

            projected, skipped = 0, 0
            for iso3, group in data.groupby("iso3_code"):
                if len(group) < MIN_HISTORY_YEARS:
                    skipped += 1
                    continue

                country_key = int(group["country_key"].iloc[0])
                years = group["year"].to_numpy(dtype=float)
                values = group["value"].to_numpy(dtype=float)

                preds, r2 = self._fit_and_predict(years, values, future_years.astype(float), method)

                if thresh:
                    preds = np.clip(preds, thresh["min"], thresh["max"])

                for year, pred in zip(future_years, preds):
                    conn.execute(
                        """
                        INSERT INTO projections (country_key, indicator_key, year, projected_value, method, confidence)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        [country_key, indicator_key, int(year), round(float(pred), 4), method, r2],
                    )
                projected += 1

            return ProjectionResult(indicator_code, short, projected, skipped, method)
        finally:
            conn.close()

    def run_all(self, method: str = "elasticnet") -> list[ProjectionResult]:
        results = []
        for code in INDICATORS:
            res = self.project_indicator(code, method=method)
            results.append(res)
            logger.info(
                f"{res.short_name}: projected {res.countries_projected} countries "
                f"({res.countries_skipped} skipped, insufficient history)"
            )
        return results


def run_projection(method: str = "elasticnet") -> list[ProjectionResult]:
    """Convenience entry point used by the CLI."""
    return Projector().run_all(method=method)
