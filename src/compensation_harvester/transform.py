
"""Normalize source attributes and validate spatial features."""

from __future__ import annotations

import logging
import re
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


# Explicit mappings for attributes observed in the official Hesse ZIP.
# Source values are preserved; only field names are normalized.
SOURCE_FIELD_MAPPING = {
    "OBJECTID": "objectid",
    "FO_KOMP_ID": "fo_komp_id",
    "GEMEINDE": "gemeinde",
    "MASS_ART": "mass_art",
    "B_BEHOERDE": "b_behoerde",
    "DAT_BESCH": "dat_besch",
    "Z_BEHOERDE": "z_behoerde",
    "AKZ": "akz",
    "SACHSTAND": "sachstand",
    "NR": "nr",
    "MASS_ID": "mass_id",
    "InfoGrafik": "info_grafik",
    "FO_ID": "fo_id",
}


def normalize_text(value: Any) -> str | None:
    """Trim whitespace and convert empty text to None."""
    if value is None or pd.isna(value):
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_column_name(name: str) -> str:
    """Convert an attribute name to stable snake_case."""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    return name.strip("_").lower()


def normalize_area_sqm(value: Any) -> float | None:
    """Parse a numeric area value without guessing its units."""
    if value is None or pd.isna(value):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number < 0:
        logger.warning("Ignoring negative area value: %r", value)
        return None

    return number


def validate_geometry(geometry: Any) -> BaseGeometry | None:
    """Return a usable geometry, repairing invalid geometry if possible."""
    if not isinstance(geometry, BaseGeometry):
        return None

    if geometry.is_empty:
        return None

    if geometry.is_valid:
        return geometry

    try:
        repaired = geometry.make_valid()
    except Exception:
        logger.warning("Geometry repair failed", exc_info=True)
        return None

    if (
        repaired is None
        or repaired.is_empty
        or not repaired.is_valid
    ):
        logger.warning("Geometry remained invalid after repair")
        return None

    return repaired


def transform_features(
    features: gpd.GeoDataFrame,
    settings: Settings | None = None,
) -> gpd.GeoDataFrame:
    """Normalize attributes, validate geometries, and project features.

    Known source fields receive explicit normalized names. Additional fields
    are retained with normalized names. The source CRS is never guessed.

    Invalid geometries are repaired when possible. Features with unusable
    geometries are dropped. Source and target CRS metadata are retained.
    """
    settings = settings or get_settings()

    if not isinstance(features, gpd.GeoDataFrame):
        raise TypeError("features must be a GeoDataFrame")

    geometry_column = features.geometry.name

    if features.crs is None and not features.empty:
        raise ValueError(
            "Source geometry has no CRS; refusing to guess its coordinate system"
        )

    # Work on a copy so the caller's input is not modified.
    result = features.copy()
    source_crs = str(features.crs) if features.crs else None

    # Map known source attributes and normalize additional field names.
    rename_map = {
        column: SOURCE_FIELD_MAPPING.get(
            str(column),
            normalize_column_name(str(column)),
        )
        for column in result.columns
        if column != geometry_column
    }
    result = result.rename(columns=rename_map)

    # Normalize string attributes after renaming, preserving other data types.
    for column in result.columns:
        if column == geometry_column:
            continue

        result[column] = result[column].map(
            lambda value: normalize_text(value)
            if isinstance(value, str)
            else value
        )

    # Validate and repair geometries, then remove unusable records.
    result[geometry_column] = result[geometry_column].map(validate_geometry)

    before = len(result)
    result = result.loc[result[geometry_column].notna()].copy()
    dropped = before - len(result)

    if dropped:
        logger.warning("Dropped %s features with unusable geometry", dropped)

    # Handle empty input or a dataset with no usable geometries.
    if result.empty:
        result = gpd.GeoDataFrame(
            result,
            geometry=geometry_column,
            crs=features.crs or settings.target_crs,
        )

        if features.crs is not None:
            result = result.to_crs(settings.target_crs)

        result["source_state_code"] = settings.source_state_code
        result["source_crs"] = source_crs
        result["target_crs"] = settings.target_crs
        return result

    # Rebuild the GeoDataFrame explicitly and project to the configured CRS.
    result = gpd.GeoDataFrame(
        result,
        geometry=geometry_column,
        crs=features.crs,
    )
    result = result.to_crs(settings.target_crs)

    # Retain provenance metadata for downstream loading and auditing.
    result["source_state_code"] = settings.source_state_code
    result["source_crs"] = source_crs
    result["target_crs"] = settings.target_crs

    return result
