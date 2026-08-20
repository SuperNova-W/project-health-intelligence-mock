"""No-op authentication layer — all requests are treated as an admin user.

Authentication has been removed so the dashboard is publicly accessible.
The ``AuthUser`` contract, ``require_roles``, ``require_project_access``, and
``visible_project_ids`` helpers are kept so the rest of the codebase compiles
unchanged; they simply no longer gate any request.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from .models import Role

# A single hardcoded admin subject used for all audit-log writes.
_PUBLIC_ADMIN = None  # resolved lazily below so import order doesn't matter


class AuthUser(BaseModel):
    """Minimal authenticated subject — always admin in the public deployment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=200)
    roles: frozenset[Role] = frozenset()

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles

    @property
    def can_view_portfolio(self) -> bool:
        return self.is_admin or Role.PORTFOLIO_LEADER in self.roles


def _public_user() -> AuthUser:
    """Return the singleton public admin user."""
    global _PUBLIC_ADMIN
    if _PUBLIC_ADMIN is None:
        _PUBLIC_ADMIN = AuthUser(
            subject="public",
            roles=frozenset({Role.ADMIN}),
        )
    return _PUBLIC_ADMIN


async def get_current_user() -> AuthUser:
    """FastAPI dependency — always returns the public admin user."""
    return _public_user()


async def get_ci_ingest_user() -> AuthUser:
    """FastAPI dependency for CI ingestion routes — same public admin."""
    return _public_user()


def require_roles(*required_roles: Role) -> Callable[..., Awaitable[AuthUser]]:
    """Build a FastAPI dependency that always passes (no roles are blocked)."""

    async def dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        return user

    return dependency


async def require_project_access(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    """Always grants access — authentication is disabled."""
    return user


def visible_project_ids(user: AuthUser, all_project_ids: list[str]) -> list[str]:
    """Returns all project ids — the public user can view everything."""
    return list(all_project_ids)
