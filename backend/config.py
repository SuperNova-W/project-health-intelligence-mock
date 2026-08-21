"""Application settings for the App Dev Horizon backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings.

    ``sqlite_path`` may be a filesystem path or ``:memory:`` for ephemeral
    in-process storage (used in tests and local dev).
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "App Dev Horizon"
    environment: str = Field(
        default="local",
        validation_alias=AliasChoices("PHI_ENVIRONMENT", "ENVIRONMENT"),
    )

    sqlite_path: str = Field(
        default="./data/project_health_intelligence.db",
        min_length=1,
        validation_alias=AliasChoices("PHI_SQLITE_PATH", "SQLITE_PATH"),
        description="Filesystem path to the SQLite database, or ':memory:' for ephemeral runs.",
    )
    sqlite_busy_timeout_ms: int = Field(default=5_000, ge=250, le=120_000)

    aggregation_floor: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices(
            "PHI_AGGREGATION_FLOOR",
            "AGGREGATION_FLOOR",
        ),
    )
    rule_set_version: str = Field(
        default="rules-v1",
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("PHI_RULE_SET_VERSION", "RULE_SET_VERSION"),
    )

    authentik_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PHI_AUTHENTIK_URL", "AUTHENTIK_URL"),
    )
    authentik_api_token: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "PHI_AUTHENTIK_API_TOKEN",
            "AUTHENTIK_API_TOKEN",
        ),
    )
    people_portal_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PHI_PEOPLE_PORTAL_URL", "PEOPLE_PORTAL_URL"),
    )
    people_portal_api_token: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "PHI_PEOPLE_PORTAL_API_TOKEN",
            "PEOPLE_PORTAL_API_TOKEN",
        ),
    )
    # LLM enrichment settings (optional; requires pip install '.[llm]')
    llm_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("PHI_LLM_ENABLED", "LLM_ENABLED"),
    )
    openai_api_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("PHI_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    llm_assessment_model: str = Field(
        default="gpt-4o",
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("PHI_LLM_ASSESSMENT_MODEL", "LLM_ASSESSMENT_MODEL"),
    )
    llm_decomposition_model: str = Field(
        default="gpt-4o",
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("PHI_LLM_DECOMPOSITION_MODEL", "LLM_DECOMPOSITION_MODEL"),
    )
    llm_timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=120.0,
        validation_alias=AliasChoices("PHI_LLM_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"),
    )
    # LLM-judged weekly signal (backend.signal_llm) -- separate from the
    # CI-assessment model/timeout above since diff-sized prompts run longer.
    llm_signal_model: str = Field(
        default="gpt-4o",
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("PHI_LLM_SIGNAL_MODEL", "LLM_SIGNAL_MODEL"),
    )
    llm_signal_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=180.0,
        validation_alias=AliasChoices("PHI_LLM_SIGNAL_TIMEOUT_SECONDS", "LLM_SIGNAL_TIMEOUT_SECONDS"),
    )
    lazy_compute_timeout_seconds: float = Field(
        default=90.0,
        ge=1.0,
        le=300.0,
        validation_alias=AliasChoices("PHI_LAZY_COMPUTE_TIMEOUT_SECONDS", "LAZY_COMPUTE_TIMEOUT_SECONDS"),
    )

    gitea_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PHI_GITEA_URL", "GITEA_URL"),
    )
    gitea_api_token: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("PHI_GITEA_API_TOKEN", "GITEA_API_TOKEN"),
    )
    gitea_org: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PHI_GITEA_ORG",
            "GITEA_ORG",
            "GITEA_ORGANIZATION",
        ),
    )

    admin_sync_token: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("PHI_ADMIN_SYNC_TOKEN", "ADMIN_SYNC_TOKEN"),
        description="Shared secret required in the X-Admin-Sync-Token header to trigger /admin/sync/* jobs.",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: Any) -> str:
        return str(value or "local").strip().lower()

    @property
    def llm_active(self) -> bool:
        """True when LLM enrichment is enabled and an API key is present."""
        return self.llm_enabled and bool(self.openai_api_key)



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings singleton."""

    return Settings()
