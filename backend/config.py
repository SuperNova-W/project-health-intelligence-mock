"""Application settings for the App Dev Horizon backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings.

    Empty ``mongo_uri`` selects the in-memory repository mode in ``db.py``.
    The dev-auth switch is deliberately opt-in and is accepted only for local
    and test environments by the auth dependency.
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

    mongo_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PHI_MONGO_URI", "MONGO_URI"),
    )
    mongo_database: str = Field(
        default="project_health_intelligence",
        validation_alias=AliasChoices("PHI_MONGO_DATABASE", "MONGO_DATABASE"),
    )
    mongo_server_selection_timeout_ms: int = Field(default=5_000, ge=250, le=120_000)

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
    authentik_oidc_issuer_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PHI_AUTHENTIK_OIDC_ISSUER_URL",
            "AUTHENTIK_OIDC_ISSUER_URL",
        ),
    )
    authentik_oidc_jwks_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PHI_AUTHENTIK_OIDC_JWKS_URL",
            "AUTHENTIK_OIDC_JWKS_URL",
        ),
    )
    authentik_oidc_audience: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PHI_AUTHENTIK_OIDC_AUDIENCE",
            "AUTHENTIK_OIDC_AUDIENCE",
        ),
    )
    authentik_oidc_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PHI_AUTHENTIK_OIDC_CLIENT_ID",
            "AUTHENTIK_OIDC_CLIENT_ID",
        ),
    )
    authentik_oidc_client_secret: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "PHI_AUTHENTIK_OIDC_CLIENT_SECRET",
            "AUTHENTIK_OIDC_CLIENT_SECRET",
        ),
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

    dev_auth: bool = Field(
        default=False,
        validation_alias=AliasChoices("PHI_DEV_AUTH", "DEV_AUTH"),
    )
    dev_auth_user_id: str = Field(
        default="dev-user",
        validation_alias=AliasChoices("PHI_DEV_AUTH_USER_ID", "DEV_AUTH_USER_ID"),
    )
    dev_auth_roles: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["portfolio_leader"],
        validation_alias=AliasChoices("PHI_DEV_AUTH_ROLES", "DEV_AUTH_ROLES"),
    )
    dev_auth_project_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "PHI_DEV_AUTH_PROJECT_IDS",
            "DEV_AUTH_PROJECT_IDS",
        ),
    )

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: Any) -> str:
        return str(value or "local").strip().lower()

    @field_validator("dev_auth_roles", "dev_auth_project_ids", mode="before")
    @classmethod
    def parse_csv_or_json_list(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @property
    def allows_dev_auth(self) -> bool:
        return self.dev_auth and self.environment in {"local", "test", "development"}

    @property
    def requires_oidc(self) -> bool:
        return not self.allows_dev_auth

    def assert_oidc_configured(self) -> None:
        """Fail closed when a non-dev deployment has no OIDC issuer."""

        if self.requires_oidc and not self.authentik_oidc_issuer_url:
            raise RuntimeError(
                "Authentik OIDC is required unless PHI_DEV_AUTH=true in a local/test environment"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings singleton."""

    return Settings()
