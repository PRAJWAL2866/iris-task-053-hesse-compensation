
import math

import pandas as pd
import pytest

from scripts.load_official_zip import is_missing_key, json_safe
from compensation_harvester.db import (
    EXPECTED_SCHEMA,
    EXPECTED_TABLE,
    _validate_staging_target,
    upsert_staging_batch,
)


@pytest.mark.parametrize(
    "value",
    [
        None,
        float("nan"),
        pd.NA,
        "",
        "   ",
    ],
)
def test_is_missing_key_for_missing_values(value):
    assert is_missing_key(value) is True


@pytest.mark.parametrize("value", ["123", 123, 0, 12.5])
def test_is_missing_key_for_valid_values(value):
    assert is_missing_key(value) is False


def test_json_safe_converts_nan_to_none():
    assert json_safe(float("nan")) is None


def test_json_safe_converts_pandas_na_to_none():
    assert json_safe(pd.NA) is None


def test_json_safe_converts_numpy_scalar():
    import numpy as np

    assert json_safe(np.int64(42)) == 42


def test_json_safe_preserves_iso_date():
    from datetime import date

    assert json_safe(date(2026, 10, 28)) == "2026-10-28"


def test_json_safe_handles_infinity_without_returning_nonstandard_json():
    # json_safe leaves infinity unchanged; the caller must ensure
    # non-standard JSON values cannot reach json.dumps(allow_nan=False).
    assert math.isinf(json_safe(float("inf")))


def test_staging_target_constants():
    assert EXPECTED_SCHEMA == "iris_staging"
    assert EXPECTED_TABLE == "compensation_sites"


def test_staging_target_rejects_other_tables():
    from compensation_harvester.config import get_settings

    settings = get_settings().model_copy(
        update={"staging_table": "production_table"}
    )

    with pytest.raises(ValueError, match="Unsafe database target"):
        _validate_staging_target(settings)


def test_empty_batch_returns_zero_without_database():
    assert upsert_staging_batch(None, []) == 0
