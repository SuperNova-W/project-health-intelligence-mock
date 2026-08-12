"""Typed errors shared by backend foundations and later API layers."""


class ProjectHealthError(Exception):
    """Base class for expected domain failures."""


class ConfigurationError(ProjectHealthError):
    """The service cannot safely start with the supplied configuration."""


class AuthenticationError(ProjectHealthError):
    """The caller could not be authenticated."""


class AuthorizationError(ProjectHealthError):
    """The authenticated caller is not allowed to access a resource."""


class PrivacyViolationError(ProjectHealthError, ValueError):
    """An individual identity or per-person metric crossed a privacy boundary."""


class EvidenceTraceError(ProjectHealthError, ValueError):
    """A warning was created without inspectable source evidence."""


class ImmutableSnapshotError(ProjectHealthError):
    """An attempt was made to mutate an already-written weekly snapshot."""
