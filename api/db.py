"""Read-only DuckDB connection dependency for API routes.

Connections are opened per-request and closed immediately after — DuckDB file
access is single-writer, so the API never opens a persistent read-write handle
that could collide with the nightly ETL cron writing to the same file. If a
request lands mid-ETL-run (a few-minute window, once a day), the connection
will fail to open; routes surface that as a 503 rather than hanging.
"""

import logging
from collections.abc import Iterator

import duckdb
from fastapi import HTTPException

from pipeline.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    try:
        conn = duckdb.connect(str(DB_PATH), read_only=True)
    except duckdb.IOException:
        logger.exception("Failed to open warehouse connection")
        raise HTTPException(status_code=503, detail="Warehouse unavailable (possibly mid-refresh). Réessaie dans un instant.")
    try:
        yield conn
    finally:
        conn.close()
