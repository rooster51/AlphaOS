"""Commercial AlphaOS tenancy boundaries.

This is an isolated domain model, not a request authenticator. Callers must
obtain AuthenticatedActor from a trusted server-side identity adapter. Legacy
research OAuth grants do not create a customer identity.
"""
from dataclasses import dataclass
from uuid import UUID


class TenantAccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class AuthenticatedActor:
    user_id: UUID
    issuer: str

    def __post_init__(self):
        if not isinstance(self.user_id, UUID) or self.user_id.int == 0 or not self.issuer:
            raise TenantAccessDenied("authenticated_user_required")


@dataclass(frozen=True)
class TenantMembership:
    tenant_id: UUID
    user_id: UUID
    role: str
    active: bool

    def __post_init__(self):
        if self.role not in ("owner", "admin", "analyst", "viewer"):
            raise TenantAccessDenied("invalid_membership_role")


@dataclass(frozen=True)
class TenantContext:
    actor: AuthenticatedActor
    tenant_id: UUID
    role: str


def authorize_tenant(actor, membership, *, operation="read"):
    """Check verified actor against a membership fetched server-side.

    Never accept a client-provided membership or tenant ID as authorization.
    A data access layer must additionally enforce tenant_id and user ownership
    through database RLS, including for nested records and joins.
    """
    if not isinstance(actor, AuthenticatedActor) or not isinstance(membership, TenantMembership):
        raise TenantAccessDenied("membership_required")
    if not membership.active or membership.user_id != actor.user_id:
        raise TenantAccessDenied("membership_required")
    if operation not in ("read", "write", "manage"):
        raise TenantAccessDenied("invalid_operation")
    if operation == "write" and membership.role == "viewer":
        raise TenantAccessDenied("insufficient_role")
    if operation == "manage" and membership.role not in ("owner", "admin"):
        raise TenantAccessDenied("insufficient_role")
    return TenantContext(actor, membership.tenant_id, membership.role)


def ledger_owner(actor):
    """Private personal journal scope is always the verified user, not tenant."""
    if not isinstance(actor, AuthenticatedActor):
        raise TenantAccessDenied("authenticated_user_required")
    return actor.user_id
