"""ML-based imputation for missing values in fact_indicators.

Strategy: missing values are filled using multivariate imputation
(KNNImputer / IterativeImputer from scikit-learn) rather than indicator-by-
indicator interpolation. For a given indicator, all other indicators in the
same pole (Economy / Health / Education / Infrastructure) are pivoted into a
wide (country, year) x indicator matrix and used as correlated context
features — e.g. under-5 mortality is imputed using health expenditure,
physicians density, immunization rates, etc. from the same country-year.

Real observed values are never modified: only cells that are NULL in
fact_indicators get written, and each imputed cell is flagged with
is_imputed=TRUE and the method used, so consumers (quality checks, API,
dashboard) can always distinguish observed from inferred data.
"""

import logging
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from sklearn.experimental import enable_iterative_imputer  # noqa: F401  (registers IterativeImputer)
from sklearn.impute import IterativeImputer, KNNImputer, SimpleImputer
from sklearn.preprocessing import StandardScaler

from .config import DB_PATH, INDICATORS, POLES
from .load import create_schema

logger = logging.getLogger(__name__)

# A pole needs at least this many (country, year) rows before we trust a
# multivariate model fit on it; below this, we skip rather than fabricate.
MIN_ROWS_FOR_IMPUTATION = 15


@dataclass
class ImputationResult:
    indicator_code: str
    short_name: str
    method: str
    total_missing: int
    imputed: int
    skipped_reason: str | None = None


class DataImputer:
    """Fills gaps in fact_indicators with multivariate ML imputation, per pole."""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path

    def _connect(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect(self.db_path)
        create_schema(conn)  # idempotent: ensures is_imputed/imputation_method exist
        return conn

    def _load_pole_matrix(self, conn: duckdb.DuckDBPyConnection, pole: str) -> pd.DataFrame:
        """Wide matrix: index=(country_iso3, year), columns=indicator short_name."""
        rows = conn.execute(
            """
            SELECT dc.iso3_code, dd.year, di.short_name, f.value
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.category = ?
            """,
            [pole],
        ).fetchdf()
        # dropna=False matters: pandas' default silently drops (country, year)
        # rows that end up all-NaN across every indicator in the pole (e.g.
        # Somalia/South Sudan in years with zero reported data at all) —
        # keeping them lets the mean-fallback below handle them explicitly
        # instead of the imputer never seeing them and undercounting.
        return rows.pivot_table(
            index=["iso3_code", "year"], columns="short_name", values="value", aggfunc="first", dropna=False
        )

    def _build_imputer(self, method: str):
        if method == "knn":
            return KNNImputer(n_neighbors=5, weights="distance")
        if method == "iterative":
            return IterativeImputer(random_state=42, max_iter=15)
        raise ValueError(f"Unknown imputation method: {method!r} (expected 'knn' or 'iterative')")

    def _real_null_keys(self, conn: duckdb.DuckDBPyConnection, indicator_code: str) -> set[tuple[str, int]]:
        """(iso3, year) pairs that actually have a NULL-valued row in fact_indicators
        for this indicator. Restricting writes to this set matters because the pole
        matrix is a union across indicators with different WB reporting windows
        (e.g. paved_roads only has rows for ~13 of the 25 years) — without this,
        we'd count/attempt to fill (country, year) cells for which no fact row
        exists at all, silently inflating the missing/imputed counters."""
        rows = conn.execute(
            """
            SELECT dc.iso3_code, dd.year
            FROM fact_indicators f
            JOIN dim_country dc ON f.country_key = dc.country_key
            JOIN dim_indicator di ON f.indicator_key = di.indicator_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE di.indicator_code = ? AND f.value IS NULL
            """,
            [indicator_code],
        ).fetchall()
        return set(rows)

    def impute_indicator(self, indicator_code: str, method: str = "knn") -> ImputationResult:
        """Impute missing values for one indicator, using its pole as context."""
        meta = INDICATORS[indicator_code]
        short = meta["short"]
        pole = meta["category"]

        conn = self._connect()
        try:
            null_keys = self._real_null_keys(conn, indicator_code)
            total_missing = len(null_keys)

            if total_missing == 0:
                return ImputationResult(indicator_code, short, method, 0, 0, "no missing values")

            wide = self._load_pole_matrix(conn, pole)
            if len(wide) < MIN_ROWS_FOR_IMPUTATION:
                return ImputationResult(indicator_code, short, method, total_missing, 0, "not enough rows in pole")

            scaler = StandardScaler()
            scaled = scaler.fit_transform(wide.values)  # NaNs are preserved through scaling

            imputer = self._build_imputer(method)
            imputed_scaled = imputer.fit_transform(scaled)

            # KNN/Iterative can still leave a cell as NaN when its entire row has
            # no observed feature in the pole to compute neighbors/regressors from
            # (e.g. a country-year with zero education data at all). Rather than
            # leave a silent gap, fall back to the column mean for just those
            # cells, and flag them with a distinct method so it's never confused
            # with a real KNN/Iterative estimate.
            fallback_mask = np.isnan(imputed_scaled)
            if fallback_mask.any():
                imputed_scaled = SimpleImputer(strategy="mean").fit_transform(imputed_scaled)

            imputed = scaler.inverse_transform(imputed_scaled)
            result_df = pd.DataFrame(imputed, index=wide.index, columns=wide.columns)
            method_df = pd.DataFrame(
                np.where(fallback_mask, f"{method}_mean_fallback", method),
                index=wide.index, columns=wide.columns,
            )

            row_mask = result_df.index.isin(null_keys)
            to_write_values = result_df[short][row_mask]
            to_write_methods = method_df[short][row_mask]

            written = self._write_back(conn, indicator_code, to_write_values, to_write_methods)
            return ImputationResult(indicator_code, short, method, total_missing, written)
        finally:
            conn.close()

    def _write_back(
        self, conn: duckdb.DuckDBPyConnection, indicator_code: str, values: pd.Series, methods: pd.Series
    ) -> int:
        indicator_key = conn.execute(
            "SELECT indicator_key FROM dim_indicator WHERE indicator_code = ?", [indicator_code]
        ).fetchone()[0]

        written = 0
        for key, value in values.items():
            if value is None or (isinstance(value, float) and np.isnan(value)):
                continue
            iso3, year = key
            conn.execute(
                """
                UPDATE fact_indicators
                SET value = ?, is_imputed = TRUE, imputation_method = ?
                WHERE indicator_key = ?
                  AND date_key = ?
                  AND value IS NULL
                  AND country_key = (SELECT country_key FROM dim_country WHERE iso3_code = ?)
                """,
                [round(float(value), 4), methods.loc[key], indicator_key, int(year), iso3],
            )
            written += 1
        return written

    def run_all(self, method: str = "knn") -> list[ImputationResult]:
        """Run imputation for every configured indicator, pole by pole."""
        results = []
        for pole in POLES:
            pole_codes = [code for code, meta in INDICATORS.items() if meta["category"] == pole]
            for code in pole_codes:
                res = self.impute_indicator(code, method=method)
                results.append(res)
                if res.skipped_reason:
                    logger.info(f"{pole}/{res.short_name}: skipped ({res.skipped_reason})")
                else:
                    logger.info(
                        f"{pole}/{res.short_name}: imputed {res.imputed}/{res.total_missing} missing values ({method})"
                    )
        total_imputed = sum(r.imputed for r in results)
        total_missing = sum(r.total_missing for r in results)
        logger.info(f"Imputation complete: {total_imputed}/{total_missing} missing values filled")
        return results


def run_imputation(method: str = "knn") -> list[ImputationResult]:
    """Convenience entry point used by the CLI."""
    return DataImputer().run_all(method=method)
