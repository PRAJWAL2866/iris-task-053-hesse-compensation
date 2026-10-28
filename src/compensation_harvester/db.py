
"""Database operations for the isolated IRIS staging schema."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

EXPECTED_SCHEMA = "iris_staging"
EXPECTED_TABLE = "compensation_sites"
EXPECTED_TARGET_CRS = "EPSG:25832"


def _validate_identifier(identifier: str) -> None:
    """Reject SQL identifiers outside a conservative allowlist."""
    if (
        not identifier
        or not identifier.replace("_", "").isalnum()
        or not identifier.isascii()
        or identifier[0].isdigit()
    ):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")


def _validate_staging_target(settings: Settings) -> None:
    """Restrict database operations to the designated staging table."""
    _validate_identifier(settings.staging_schema)
    _validate_identifier(settings.staging_table)

    if (
        settings.staging_schema != EXPECTED_SCHEMA
        or settings.staging_table != EXPECTED_TABLE
    ):
        raise ValueError(
            "Unsafe database target: operations are restricted to "
            f"{EXPECTED_SCHEMA}.{EXPECTED_TABLE}"
        )


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database."""
    settings = settings or get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def ensure_staging_table(
    engine: Engine,
    settings: Settings | None = None,
) -> None:
    """Create the isolated staging schema and table if needed."""
    settings = settings or get_settings()
    _validate_staging_target(settings)

    schema = settings.staging_schema
    table = settings.staging_table

    ddl_statements = [
        f'CREATE SCHEMA IF NOT EXISTS "{schema}"',
        f"""
        CREATE TABLE IF NOT EXISTS "{schema}"."{table}" (
            record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            state_code TEXT NOT NULL,
            site_id TEXT NOT NULL,
            source_properties JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            source_crs TEXT,
            target_crs TEXT NOT NULL DEFAULT '{EXPECTED_TARGET_CRS}',
            geom geometry(Geometry, 25832),
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (site_id, state_code)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS "{table}_geom_gix"
        ON "{schema}"."{table}" USING GIST (geom)
        """,
    ]

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        for statement in ddl_statements:
            connection.execute(text(statement))

    logger.info("Staging table is ready: %s.%s", schema, table)


def upsert_staging_record(
    engine: Engine,
    *,
    state_code: str,
    site_id: str,
    source_properties: dict[str, Any],
    geometry_wkt: str | None,
    source_crs: str | None,
    target_crs: str = EXPECTED_TARGET_CRS,
    settings: Settings | None = None,
) -> None:
    """Insert or update one record using its stable source key."""
    settings = settings or get_settings()
    _validate_staging_target(settings)

    if not state_code.strip() or not site_id.strip():
        raise ValueError("state_code and site_id must be non-empty")

    if target_crs != EXPECTED_TARGET_CRS:
        raise ValueError(
            f"target_crs must be {EXPECTED_TARGET_CRS!r}, got {target_crs!r}"
        )

    schema = settings.staging_schema
    table = settings.staging_table

    sql = text(f"""
        INSERT INTO "{schema}"."{table}" (
            state_code, site_id, source_properties, source_crs,
            target_crs, geom
        )
        VALUES (
            :state_code,
            :site_id,
            CAST(:source_properties AS jsonb),
            :source_crs,
            :target_crs,
            ST_SetSRID(ST_GeomFromText(:geometry_wkt), 25832)
        )
        ON CONFLICT (site_id, state_code) DO UPDATE SET
            source_properties = EXCLUDED.source_properties,
            source_crs = EXCLUDED.source_crs,
            target_crs = EXCLUDED.target_crs,
            geom = EXCLUDED.geom,
            last_seen_at = NOW()
    """)

    with engine.begin() as connection:
        connection.execute(
            sql,
            {
                "state_code": state_code.strip(),
                "site_id": site_id.strip(),
                "source_properties": json.dumps(
                    source_properties, ensure_ascii=False, default=str
                ),
                "source_crs": source_crs,
                "target_crs": target_crs,
                "geometry_wkt": geometry_wkt,
            },
        )


def staging_count(
    engine: Engine,
    settings: Settings | None = None,
) -> int:
    """Return the current number of records in the staging table."""
    settings = settings or get_settings()
    _validate_staging_target(settings)

    schema = settings.staging_schema
    table = settings.staging_table

    with engine.connect() as connection:
        result = connection.execute(
            text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        )
        return int(result.scalar_one())


def upsert_staging_batch(
    engine: Engine,
    records: list[dict[str, Any]],
    settings: Settings | None = None,
) -> int:
    """Upsert a batch atomically and return the number of rows processed."""
    settings = settings or get_settings()
    _validate_staging_target(settings)

    if not records:
        return 0

    for record in records:
        if not record.get("state_code") or not str(
            record["state_code"]
        ).strip():
            raise ValueError("Every record must have a non-empty state_code")

        if not record.get("site_id") or not str(
            record["site_id"]
        ).strip():
            raise ValueError("Every record must have a non-empty site_id")

        if record.get("target_crs") != EXPECTED_TARGET_CRS:
            raise ValueError(
                f"Every record target_crs must be {EXPECTED_TARGET_CRS!r}"
            )

    schema = settings.staging_schema
    table = settings.staging_table

    sql = text(f"""
        INSERT INTO "{schema}"."{table}" (
            state_code, site_id, source_properties,
            source_crs, target_crs, geom
        )
        VALUES (
            :state_code, :site_id, CAST(:source_properties AS jsonb),
            :source_crs, :target_crs,
            ST_SetSRID(ST_GeomFromText(:geometry_wkt), 25832)
        )
        ON CONFLICT (site_id, state_code) DO UPDATE SET
            source_properties = EXCLUDED.source_properties,
            source_crs = EXCLUDED.source_crs,
            target_crs = EXCLUDED.target_crs,
            geom = EXCLUDED.geom,
            last_seen_at = NOW()
    """)

    with engine.begin() as connection:
        connection.execute(sql, records)

    return len(records)
