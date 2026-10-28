
"""Load the official Hessen compensation ZIP into the isolated staging table.

This is a documented fallback, not a substitute for a successful live WFS read.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from compensation_harvester.config import get_settings
from compensation_harvester.db import (
    create_db_engine,
    ensure_staging_table,
    upsert_staging_batch,
)
from compensation_harvester.transform import transform_features

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ARCHIVE = Path("data/Komp_Hessen_utm.zip")
SHAPEFILE = "Komp_Hessen_UTM.shp"
BATCH_SIZE = 500


def is_missing_key(value: Any) -> bool:
    """Return True for null, NaN, or blank source-key values."""
    if value is None:
        return True

    try:
        missing = pd.isna(value)
        if getattr(missing, "ndim", 0) == 0 and bool(missing):
            return True
    except (TypeError, ValueError):
        pass

    return isinstance(value, str) and not value.strip()


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy values to JSON-compatible Python values."""
    if value is None:
        return None

    try:
        missing = pd.isna(value)
        if getattr(missing, "ndim", 0) == 0 and bool(missing):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if isinstance(value, (str, int, float, bool, list, dict)):
        return value

    return str(value)


def main() -> None:
    if not ARCHIVE.exists():
        raise FileNotFoundError(
            f"{ARCHIVE} not found. Run this script from the project root."
        )

    archive = ARCHIVE.resolve()
    source = f"zip://{archive.as_posix()}!{SHAPEFILE}"

    logger.info("Reading official Hessen compensation dataset: %s", archive)
    features = gpd.read_file(source)

    if features.empty:
        raise ValueError("The official ZIP contains no features.")

    if features.crs is None:
        raise ValueError("Source CRS is missing; refusing to guess coordinates.")

    original_crs = str(features.crs)
    source_count = len(features)

    missing_geometry = int(features.geometry.isna().sum())
    non_null_geometry = features.geometry.notna()
    invalid_before = int(
        (non_null_geometry & ~features.geometry.is_valid).sum()
    )

    logger.info(
        "Read %s features; CRS=%s; invalid=%s; missing geometry=%s",
        source_count,
        original_crs,
        invalid_before,
        missing_geometry,
    )

    # Preserve source attributes and index for provenance after geometry repair.
    original_attributes = [
        column for column in features.columns
        if column != features.geometry.name
    ]

    # Repair invalid geometries where possible.
    invalid_mask = features.geometry.notna() & ~features.geometry.is_valid
    if invalid_mask.any():
        features.loc[invalid_mask, features.geometry.name] = (
            features.loc[invalid_mask].geometry.make_valid()
        )

    # Remove missing, empty, or still-invalid geometry before transformation.
    geometry = features.geometry
    usable_geometry = (
        geometry.notna()
        & ~geometry.is_empty
        & geometry.is_valid
    )
    dropped_geometry = int((~usable_geometry).sum())

    if dropped_geometry:
        logger.warning(
            "Dropping %s features with missing, empty, or still-invalid geometry",
            dropped_geometry,
        )

    features = features.loc[usable_geometry].copy()

    if features.empty:
        raise ValueError("No usable geometries remain after validation.")

    settings = get_settings()
    transformed = transform_features(features, settings)

    engine = create_db_engine(settings)
    upserted = 0
    skipped_missing_key = 0
    skipped_geometry = 0
    batch: list[dict[str, Any]] = []

    try:
        ensure_staging_table(engine, settings)

        for index, row in transformed.iterrows():
            compensation_id = row.get("fo_komp_id")
            measure_id = row.get("mass_id")

            if (
                is_missing_key(compensation_id)
                or is_missing_key(measure_id)
            ):
                skipped_missing_key += 1
                logger.warning(
                    "Skipping row %s: composite source key is missing",
                    index,
                )
                continue

            geometry = row.geometry
            if (
                geometry is None
                or geometry.is_empty
                or not geometry.is_valid
            ):
                skipped_geometry += 1
                logger.warning(
                    "Skipping row %s: transformed geometry is unusable",
                    index,
                )
                continue

            site_id = (
                f"{str(compensation_id).strip()}:"
                f"{str(measure_id).strip()}"
            )

            # Keep original source column names and values as provenance.
            source_row = features.loc[index]
            properties = {
                column: json_safe(source_row[column])
                for column in original_attributes
            }

            batch.append(
                {
                    "state_code": settings.source_state_code,
                    "site_id": site_id,
                    "source_properties": json.dumps(
                        properties,
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    "geometry_wkt": geometry.wkt,
                    "source_crs": original_crs,
                    "target_crs": settings.target_crs,
                }
            )

            if len(batch) >= BATCH_SIZE:
                upserted += upsert_staging_batch(engine, batch, settings)
                logger.info("Upserted %s records so far", upserted)
                batch = []

        if batch:
            upserted += upsert_staging_batch(engine, batch, settings)

    finally:
        engine.dispose()

    logger.info(
        "Official ZIP load summary: source=%s, upserted=%s, "
        "skipped_missing_key=%s, skipped_geometry=%s, "
        "invalid_before=%s, dropped_geometry=%s",
        source_count,
        upserted,
        skipped_missing_key,
        skipped_geometry,
        invalid_before,
        dropped_geometry,
    )


if __name__ == "__main__":
    main()
