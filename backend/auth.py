"""Authentik OIDC authentication and server-side role/project scoping."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings, get_settings
from .errors import AuthenticationError
from .models import ProjectId, Role


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class AuthUser(BaseModel):
    """Minimal authenticated subject; raw claims are intentionally discarded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=200)
    roles: frozenset[Role] = frozenset()
    project_ids: frozenset[ProjectId] = frozenset()

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> "AuthUser":
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("OIDC token has no subject")

        raw_roles: list[Any] = []
        for claim_name in ("roles", "groups", "authentik_groups"):
            value = claims.get(claim_name, [])
            if isinstance(value, str):
                raw_roles.append(value)
            elif isinstance(value, list):
                raw_roles.extend(value)

        roles: set[Role] = set()
        for raw_role in raw_roles:
            normalized = str(raw_role).strip().lower().replace("-", "_").split("/")[-1]
            try:
                roles.add(Role(normalized))
            except ValueError:
                continue

        raw_project_ids = claims.get("project_ids", claims.get("phi_project_ids", []))
        if isinstance(raw_project_ids, str):
            raw_project_ids = [raw_project_ids]
        project_ids = frozenset(str(project_id) for project_id in (raw_project_ids or []))
        return cls(subject=subject, roles=frozenset(roles), project_ids=project_ids)

    @classmethod
    def from_dev_settings(cls, settings: Settings) -> "AuthUser":
        if not settings.allows_dev_auth:
            raise AuthenticationError(
                "dev auth requires PHI_DEV_AUTH=true in local, test, or development environment"
            )
        roles: set[Role] = set()
        for raw_role in settings.dev_auth_roles:
            try:
                roles.add(Role(str(raw_role).strip().lower().replace("-", "_")))
            except ValueError:
                continue
        return cls(
            subject=settings.dev_auth_user_id,
            roles=frozenset(roles),
            project_ids=frozenset(settings.dev_auth_project_ids),
        )

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles

    @property
    def can_view_portfolio(self) -> bool:
        return self.is_admin or Role.PORTFOLIO_LEADER in self.roles


async def _oidc_metadata(settings: Settings) -> dict[str, Any]:
    issuer = (settings.authentik_oidc_issuer_url or "").rstrip("/")
    if not issuer:
        raise AuthenticationError("Authentik OIDC issuer is not configured")
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        return response.json()


async def verify_oidc_token(token: str, settings: Settings) -> AuthUser:
    """Validate a signed Authentik JWT using the issuer's published key set."""

    try:
        unverified_header = jwt.get_unverified_header(token)
        metadata = await _oidc_metadata(settings)
        jwks_url = settings.authentik_oidc_jwks_url or metadata.get("jwks_uri")
        if not jwks_url:
            raise AuthenticationError("OIDC JWKS endpoint is not configured")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            keys = response.json().get("keys", [])

        key_id = unverified_header.get("kid")
        jwk = next((item for item in keys if item.get("kid") == key_id), None)
        if jwk is None:
            raise AuthenticationError("OIDC signing key was not found")

        signing_key = jwt.PyJWK.from_dict(jwk).key
        algorithm = unverified_header.get("alg")
        if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
            raise AuthenticationError("OIDC token uses an unsupported signing algorithm")

        audience = settings.authentik_oidc_audience
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=audience if audience else None,
            issuer=(settings.authentik_oidc_issuer_url or "").rstrip("/"),
            options={
                "require": ["sub", "iss", "exp"],
                "verify_aud": bool(audience),
            },
        )
        return AuthUser.from_claims(claims)
    except AuthenticationError:
        raise
    except (jwt.PyJWTError, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        raise AuthenticationError("OIDC token validation failed") from exc


async def get_dev_auth_user(settings: Settings = Depends(get_settings)) -> AuthUser:
    """Explicit local/test dependency; never a production fallback."""

    return AuthUser.from_dev_settings(settings)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthUser:
    """Authenticate with explicit dev auth or Authentik OIDC, failing closed."""

    if settings.allows_dev_auth:
        return AuthUser.from_dev_settings(settings)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    try:
        return await verify_oidc_token(token, settings)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC authentication failed",
        ) from exc


def require_roles(*required_roles: Role) -> Callable[..., Awaitable[AuthUser]]:
    """Build a FastAPI dependency enforcing role claims server-side."""

    async def dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.is_admin or any(role in user.roles for role in required_roles):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")

    return dependency


async def require_project_access(
    project_id: ProjectId,
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    """Enforce project-lead scoping in the backend, not in the frontend."""

    if user.can_view_portfolio or project_id in user.project_ids:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")


def visible_project_ids(user: AuthUser, all_project_ids: list[ProjectId]) -> list[ProjectId]:
    """Return the server-side project scope for queue and detail queries."""

    if user.can_view_portfolio:
        return list(all_project_ids)
    return [project_id for project_id in all_project_ids if project_id in user.project_ids]
