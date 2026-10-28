
"""Orchestrate WFS retrieval, transformation, and staging ingestion."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .config import Settings, get_settings
from .db import (
    create_db_engine,
    ensure_staging_table,
    staging_count,
    upsert_staging_record,
)
from .transform import transform_features
from .wfs_client import WFSClient

logger = logging.getLogger(__name__)


def _json_safe_properties(
    row: Any,
    geometry_column: str,
) -> dict[str, Any]:
    """Convert source attributes into JSON-compatible Python values."""
    properties: dict[str, Any] = {}

    for key, value in row.items():
        if key == geometry_column:
            continue

        if value is None:
            properties[key] = None
            continue

        # Convert NumPy and pandas scalar values to Python scalars.
        if hasattr(value, "item"):
            try:
                value = value.item()
            except (ValueError, TypeError):
                pass

        # Convert missing values (NaN, NaT, pandas NA) to None.
        try:
            if pd.isna(value):
                value = None
        except (TypeError, ValueError):
            # pd.isna can return an array for non-scalar values.
            pass

        if value is not None and not isinstance(
            value, (str, int, float, bool, list, dict)
        ):
            value = str(value)

        properties[key] = value

    return properties


def _get_source_id(properties: dict[str, Any]) -> str | None:
    """Build a staging identifier from the documented composite source key.

    Do not fall back to OBJECTID, FID, or other identifiers whose stability
    across source snapshots has not been established.
    """
    compensation_id = properties.get("fo_komp_id")
    measure_id = properties.get("mass_id")

    if compensation_id in (None, "") or measure_id in (None, ""):
        return None

    return f"{compensation_id}:{measure_id}"


def run_pipeline(
    settings: Settings | None = None,
    client: WFSClient | None = None,
) -> dict[str, int]:
    """Fetch, transform, and idempotently upsert source records into staging."""
    settings = settings or get_settings()
    client = client or WFSClient(settings)

    logger.info("Starting Hesse compensation register ingestion")

    engine = create_db_engine(settings)

    try:
        ensure_staging_table(engine, settings)

        features = client.fetch_features()
        fetched_count = len(features)

        if features.empty:
            logger.warning("The WFS returned no features")

            return {
                "fetched": 0,
                "transformed": 0,
                "upserted": 0,
                "skipped_missing_id": 0,
                "staging_total": staging_count(engine, settings),
            }

        transformed = transform_features(features, settings)
        geometry_column = transformed.geometry.name

        upserted_count = 0
        skipped_count = 0

        for _, row in transformed.iterrows():
            properties = _json_safe_properties(row, geometry_column)
            source_id = _get_source_id(properties)

            if source_id is None:
                logger.warning(
                    "Skipping feature without both FO_KOMP_ID and MASS_ID"
                )
                skipped_count += 1
                continue

            geometry = row[geometry_column]

            source_crs_value = row.get("source_crs")
            source_crs = (
                str(source_crs_value)
                if source_crs_value is not None
                else None
            )

            upsert_staging_record(
                engine,
                state_code=settings.source_state_code,
                site_id=source_id,
                source_properties=properties,
                geometry_wkt=geometry.wkt if geometry is not None else None,
                source_crs=source_crs,
                target_crs=settings.target_crs,
                settings=settings,
            )

            upserted_count += 1

        result = {
            "fetched": fetched_count,
            "transformed": len(transformed),
            "upserted": upserted_count,
            "skipped_missing_id": skipped_count,
            "staging_total": staging_count(engine, settings),
        }

        logger.info("Ingestion summary: %s", result)
        return result

    finally:
        engine.dispose()
