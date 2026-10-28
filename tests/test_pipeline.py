
import geopandas as gpd
import pytest
from shapely.geometry import Point

from src.compensation_harvester.config import Settings
from src.compensation_harvester import pipeline


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        staging_schema="iris_staging",
        staging_table="compensation_sites",
        target_crs="EPSG:25832",
        source_state_code="HE",
    )


def test_pipeline_uses_composite_source_id(settings, monkeypatch):
    features = gpd.GeoDataFrame(
        {
            "FO_KOMP_ID": ["K100"],
            "MASS_ID": ["M200"],
        },
        geometry=[Point(8.0, 50.0)],
        crs="EPSG:4326",
    )

    transformed = gpd.GeoDataFrame(
        {
            "fo_komp_id": ["K100"],
            "mass_id": ["M200"],
            "source_crs": ["EPSG:4326"],
            "target_crs": ["EPSG:25832"],
        },
        geometry=[Point(500000, 5500000)],
        crs="EPSG:25832",
    )

    class FakeClient:
        def __init__(self, settings):
            pass

        def fetch_features(self):
            return features

    writes = []

    monkeypatch.setattr(pipeline, "create_db_engine", lambda settings: object())
    monkeypatch.setattr(pipeline, "ensure_staging_table", lambda engine, settings: None)
    monkeypatch.setattr(pipeline, "staging_count", lambda engine, settings: 1)
    monkeypatch.setattr(pipeline, "transform_features", lambda features, settings: transformed)
    monkeypatch.setattr(pipeline, "upsert_staging_record", lambda *args, **kwargs: writes.append(kwargs))
    monkeypatch.setattr(pipeline, "WFSClient", FakeClient)

    class FakeEngine:
        def dispose(self):
            pass

    monkeypatch.setattr(pipeline, "create_db_engine", lambda settings: FakeEngine())

    result = pipeline.run_pipeline(settings=settings)

    assert result["fetched"] == 1
    assert result["transformed"] == 1
    assert result["upserted"] == 1
    assert writes[0]["site_id"] == "K100:M200"
    assert writes[0]["source_crs"] == "EPSG:4326"
    assert writes[0]["target_crs"] == "EPSG:25832"


def test_pipeline_skips_feature_without_stable_id(settings, monkeypatch):
    features = gpd.GeoDataFrame(
        {"description": ["no source identifier"]},
        geometry=[Point(8.0, 50.0)],
        crs="EPSG:4326",
    )

    transformed = gpd.GeoDataFrame(
        {"description": ["no source identifier"]},
        geometry=[Point(500000, 5500000)],
        crs="EPSG:25832",
    )

    class FakeClient:
        def __init__(self, settings):
            pass

        def fetch_features(self):
            return features

    class FakeEngine:
        def dispose(self):
            pass

    monkeypatch.setattr(pipeline, "create_db_engine", lambda settings: FakeEngine())
    monkeypatch.setattr(pipeline, "ensure_staging_table", lambda engine, settings: None)
    monkeypatch.setattr(pipeline, "staging_count", lambda engine, settings: 0)
    monkeypatch.setattr(pipeline, "transform_features", lambda features, settings: transformed)
    monkeypatch.setattr(pipeline, "WFSClient", FakeClient)

    def unexpected_write(*args, **kwargs):
        pytest.fail("Pipeline should not write a feature without a stable ID")

    monkeypatch.setattr(pipeline, "upsert_staging_record", unexpected_write)

    result = pipeline.run_pipeline(settings=settings)

    assert result["fetched"] == 1
    assert result["transformed"] == 1
    assert result["upserted"] == 0
    assert result["skipped_missing_id"] == 1


def test_pipeline_empty_source_does_not_write(settings, monkeypatch):
    features = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    class FakeClient:
        def __init__(self, settings):
            pass

        def fetch_features(self):
            return features

    class FakeEngine:
        def dispose(self):
            pass

    monkeypatch.setattr(pipeline, "create_db_engine", lambda settings: FakeEngine())
    monkeypatch.setattr(pipeline, "ensure_staging_table", lambda engine, settings: None)
    monkeypatch.setattr(pipeline, "staging_count", lambda engine, settings: 0)
    monkeypatch.setattr(pipeline, "WFSClient", FakeClient)

    def unexpected_write(*args, **kwargs):
        pytest.fail("Empty source must not write records")

    monkeypatch.setattr(pipeline, "upsert_staging_record", unexpected_write)

    result = pipeline.run_pipeline(settings=settings)

    assert result["fetched"] == 0
    assert result["transformed"] == 0
    assert result["upserted"] == 0
    assert result["staging_total"] == 0



def test_pipeline_skips_objectid_without_composite_key(settings, monkeypatch):
    features = gpd.GeoDataFrame(
        {"OBJECTID": [123]},
        geometry=[Point(8.0, 50.0)],
        crs="EPSG:4326",
    )

    transformed = gpd.GeoDataFrame(
        {
            "objectid": [123],
            "source_crs": ["EPSG:4326"],
            "target_crs": ["EPSG:25832"],
        },
        geometry=[Point(500000, 5500000)],
        crs="EPSG:25832",
    )

    class FakeClient:
        def __init__(self, settings):
            pass

        def fetch_features(self):
            return features

    class FakeEngine:
        def dispose(self):
            pass

    monkeypatch.setattr(
        pipeline, "create_db_engine", lambda settings: FakeEngine()
    )
    monkeypatch.setattr(
        pipeline, "ensure_staging_table", lambda engine, settings: None
    )
    monkeypatch.setattr(
        pipeline, "staging_count", lambda engine, settings: 0
    )
    monkeypatch.setattr(
        pipeline,
        "transform_features",
        lambda features, settings: transformed,
    )
    monkeypatch.setattr(pipeline, "WFSClient", FakeClient)

    def unexpected_write(*args, **kwargs):
        pytest.fail("OBJECTID alone must not be used as a stable source ID")

    monkeypatch.setattr(
        pipeline, "upsert_staging_record", unexpected_write
    )

    result = pipeline.run_pipeline(settings=settings)

    assert result["fetched"] == 1
    assert result["transformed"] == 1
    assert result["upserted"] == 0
    assert result["skipped_missing_id"] == 1
