
"""Application configuration for the Hesse compensation harvester."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load settings from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    wfs_url: str = Field(
        default="https://gds.hessen.de/wfs/hlnug/kompensation",
        validation_alias=AliasChoices("WFS_BASE_URL", "wfs_url"),
    )
    wfs_layer: str = Field(
        default="he_kompensationskataster",
        validation_alias=AliasChoices("WFS_LAYER", "wfs_layer"),
    )
    request_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias=AliasChoices(
            "WFS_TIMEOUT_SECONDS", "request_timeout"
        ),
    )
    page_size: int = Field(
        default=500,
        ge=1,
        le=5000,
        validation_alias=AliasChoices("WFS_PAGE_SIZE", "page_size"),
    )
    target_crs: str = Field(
        default="EPSG:25832",
        validation_alias=AliasChoices("TARGET_CRS", "target_crs"),
    )
    source_state_code: str = Field(
        default="HE",
        validation_alias=AliasChoices(
            "SOURCE_STATE_CODE", "source_state_code"
        ),
    )
    staging_schema: str = Field(
        default="iris_staging",
        validation_alias=AliasChoices("STAGING_SCHEMA", "staging_schema"),
    )
    staging_table: str = Field(
        default="compensation_sites",
        validation_alias=AliasChoices("STAGING_TABLE", "staging_table"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
