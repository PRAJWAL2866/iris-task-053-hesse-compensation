import pytest

from src.compensation_harvester.config import Settings
from src.compensation_harvester.db import (
    _validate_identifier,
    ensure_staging_table,
    staging_count,
    upsert_staging_batch,
    upsert_staging_record,
)


@pytest.fixture
def unsafe_settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        staging_schema="public",
        staging_table="compensation_sites",
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda engine, settings: ensure_staging_table(engine, settings),
        lambda engine, settings: staging_count(engine, settings),
        lambda engine, settings: upsert_staging_batch(engine, [], settings),
        lambda engine, settings: upsert_staging_record(
            engine,
            state_code="HE",
            site_id="test:1",
            source_properties={},
            geometry_wkt=None,
            source_crs="EPSG:25832",
            settings=settings,
        ),
    ],
)
def test_database_operations_reject_unsafe_target(
    operation, unsafe_settings
):
    assert unsafe_settings.staging_schema == "public"

    with pytest.raises(ValueError, match="Unsafe database target"):
        operation(object(), unsafe_settings)


def test_invalid_sql_identifier_is_rejected():
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        _validate_identifier("public; DROP TABLE users")
