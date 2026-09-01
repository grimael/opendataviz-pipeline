"""Load transformed data into DuckDB with a star schema."""

import duckdb
import logging
from typing import Any
from .config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection, creating the DB if needed."""
    return duckdb.connect(str(DB_PATH))


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create star schema tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_country (
            country_key INTEGER PRIMARY KEY,
            iso3_code VARCHAR(3) NOT NULL,
            iso2_code VARCHAR(2),
            country_name VARCHAR NOT NULL,
            region VARCHAR,
            income_level VARCHAR,
            capital_city VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_indicator (
            indicator_key INTEGER PRIMARY KEY,
            indicator_code VARCHAR NOT NULL,
            indicator_name VARCHAR NOT NULL,
            category VARCHAR,
            unit VARCHAR,
            short_name VARCHAR
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_date (
            date_key INTEGER PRIMARY KEY,
            year INTEGER NOT NULL,
            decade VARCHAR,
            is_recent BOOLEAN
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fact_indicators (
            country_key INTEGER,
            indicator_key INTEGER,
            date_key INTEGER,
            value DOUBLE,
            yoy_change DOUBLE,
            is_imputed BOOLEAN DEFAULT FALSE,
            imputation_method VARCHAR,
            extracted_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (country_key, indicator_key, date_key)
        )
    """)

    # Migration for warehouses created before the imputation columns existed
    conn.execute("ALTER TABLE fact_indicators ADD COLUMN IF NOT EXISTS is_imputed BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE fact_indicators ADD COLUMN IF NOT EXISTS imputation_method VARCHAR")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS projections (
            country_key INTEGER,
            indicator_key INTEGER,
            year INTEGER,
            projected_value DOUBLE,
            method VARCHAR,
            confidence DOUBLE,
            generated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (country_key, indicator_key, year)
        )
    """)
    conn.execute("ALTER TABLE projections ADD COLUMN IF NOT EXISTS confidence DOUBLE")

    logger.info("Schema created/verified")


def load_dimensions(conn: duckdb.DuckDBPyConnection, data: dict[str, list[dict]]) -> None:
    """Load dimension tables (upsert pattern: delete + insert)."""
    # dim_country
    conn.execute("DELETE FROM dim_country")
    for row in data["dim_country"]:
        conn.execute("""
            INSERT INTO dim_country (country_key, iso3_code, iso2_code, country_name, region)
            VALUES (?, ?, ?, ?, ?)
        """, [row["country_key"], row["iso3_code"], row["iso2_code"], 
              row["country_name"], row["region"]])
    logger.info(f"Loaded {len(data['dim_country'])} countries")
    
    # dim_indicator
    conn.execute("DELETE FROM dim_indicator")
    for row in data["dim_indicator"]:
        conn.execute("""
            INSERT INTO dim_indicator (indicator_key, indicator_code, indicator_name, category, unit, short_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [row["indicator_key"], row["indicator_code"], row["indicator_name"],
              row["category"], row["unit"], row["short_name"]])
    logger.info(f"Loaded {len(data['dim_indicator'])} indicators")
    
    # dim_date
    conn.execute("DELETE FROM dim_date")
    for row in data["dim_date"]:
        conn.execute("""
            INSERT INTO dim_date (date_key, year, decade, is_recent)
            VALUES (?, ?, ?, ?)
        """, [row["date_key"], row["year"], row["decade"], row["is_recent"]])
    logger.info(f"Loaded {len(data['dim_date'])} date records")


def load_facts(conn: duckdb.DuckDBPyConnection, facts: list[dict]) -> None:
    """Load fact table with upsert (INSERT OR REPLACE)."""
    conn.execute("DELETE FROM fact_indicators")
    
    batch_size = 1000
    total = 0
    for i in range(0, len(facts), batch_size):
        batch = facts[i:i + batch_size]
        for row in batch:
            conn.execute("""
                INSERT INTO fact_indicators (country_key, indicator_key, date_key, value, yoy_change)
                VALUES (?, ?, ?, ?, ?)
            """, [row["country_key"], row["indicator_key"], row["date_key"],
                  row["value"], row["yoy_change"]])
        total += len(batch)
    
    logger.info(f"Loaded {total} fact records")


def update_country_metadata(conn: duckdb.DuckDBPyConnection, metadata: dict[str, dict]) -> None:
    """Update country dimension with metadata from World Bank API."""
    for iso3, meta in metadata.items():
        conn.execute("""
            UPDATE dim_country 
            SET income_level = ?, capital_city = ?, latitude = ?, longitude = ?
            WHERE iso3_code = ?
        """, [meta.get("income_level"), meta.get("capital_city"),
              meta.get("latitude", 0), meta.get("longitude", 0), iso3])
    logger.info(f"Updated metadata for {len(metadata)} countries")


def load_all(data: dict[str, list[dict]], country_metadata: dict[str, dict] | None = None) -> None:
    """Full load: create schema, load all dimensions and facts."""
    conn = get_connection()
    try:
        create_schema(conn)
        load_dimensions(conn, data)
        load_facts(conn, data["facts"])
        if country_metadata:
            update_country_metadata(conn, country_metadata)
        
        # Verify
        count = conn.execute("SELECT COUNT(*) FROM fact_indicators").fetchone()[0]
        logger.info(f"Load complete. Total facts in warehouse: {count}")
    finally:
        conn.close()
