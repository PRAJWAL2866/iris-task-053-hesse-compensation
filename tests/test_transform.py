import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, Point

from src.compensation_harvester.transform import (
    normalize_area_sqm,
    normalize_column_name,
    normalize_text,
    transform_features,
)


def test_normalize_text():
    assert normalize_text("  Darmstadt   Mitte ") == "Darmstadt Mitte"
    assert normalize_text("   ") is None
    assert normalize_text(None) is None


def test_normalize_column_name():
    assert normalize_column_name("MunicipalityName") == "municipality_name"
    assert normalize_column_name("AREA (sqm)") == "area_sqm"


def test_normalize_area_sqm():
    assert normalize_area_sqm("125.5") == 125.5
    assert normalize_area_sqm(-10) is None
    assert normalize_area_sqm("unknown") is None
    assert normalize_area_sqm(None) is None


def test_transform_projects_geometry_to_target_crs():
    features = gpd.GeoDataFrame(
        {
            "MunicipalityName": ["Darmstadt"],
            "AREA_SQM": [125.5],
        },
        geometry=[Point(8.65, 49.87)],
        crs="EPSG:4326",
    )

    result = transform_features(features)

    assert result.crs.to_epsg() == 25832
    assert result.iloc[0]["municipality_name"] == "Darmstadt"
    assert result.iloc[0]["source_state_code"] == "HE"
    assert result.geometry.iloc[0].x > 0


def test_transform_drops_empty_geometry():
    features = gpd.GeoDataFrame(
        {"name": ["valid", "empty"]},
        geometry=[Point(8.65, 49.87), None],
        crs="EPSG:4326",
    )

    result = transform_features(features)

    assert len(result) == 1
    assert result.iloc[0]["name"] == "valid"


def test_transform_refuses_missing_crs():
    features = gpd.GeoDataFrame(
        {"name": ["unknown_crs"]},
        geometry=[Point(8.65, 49.87)],
    )

    try:
        transform_features(features)
    except ValueError as exc:
        assert "no CRS" in str(exc)
    else:
        raise AssertionError("Expected missing CRS to be rejected")


def test_transform_maps_official_hesse_source_fields():
    features = gpd.GeoDataFrame(
        {
            "FO_KOMP_ID": ["35297"],
            "MASS_ID": ["64369"],
            "GEMEINDE": [" Frankfurt am Main "],
            "MASS_ART": ["Ausgleich"],
            "SACHSTAND": ["abgeschlossen"],
            "FO_ID": [None],
        },
        geometry=[Point(8.6821, 50.1109)],
        crs="EPSG:4326",
    )

    result = transform_features(features)

    assert result.iloc[0]["fo_komp_id"] == "35297"
    assert result.iloc[0]["mass_id"] == "64369"
    assert result.iloc[0]["gemeinde"] == "Frankfurt am Main"
    assert result.iloc[0]["mass_art"] == "Ausgleich"
    assert result.iloc[0]["sachstand"] == "abgeschlossen"
    assert pd.isna(result.iloc[0]["fo_id"])