"""Fail-closed identity boundary for future owner-scoped ledger operations.

This module deliberately does not authenticate requests or write records. It
accepts only a verified identity from a future trusted authentication adapter.
Legacy shared-token and process-local OAuth grants are research-only.
"""
from dataclasses import dataclass
from uuid import UUID


class IdentityUnavailable(PermissionError):
    """No trustworthy, user-bound ledger principal was established."""


@dataclass(frozen=True)
class LedgerPrincipal:
    user_id: UUID
    issuer: str
    audience: str


def require_ledger_principal(*, verified_subject=None, issuer=None,
                             audience=None, verified=False):
    """Return a principal only after external cryptographic verification.

    The caller must verify signature, expiration, issuer, audience, token type,
    and revocation/session requirements with a trusted identity provider.
    Never accept an arbitrary UUID, MCP client ID, shared API token, or the
    legacy OAuth literal 'owner' as proof of ownership.
    """
    if not verified or not issuer or not audience or not verified_subject:
        raise IdentityUnavailable("verified_user_identity_required")
    if verified_subject == "owner":
        raise IdentityUnavailable("verified_user_identity_required")
    try:
        user_id = UUID(str(verified_subject))
    except (TypeError, ValueError, AttributeError):
        raise IdentityUnavailable("verified_user_identity_required") from None
    if user_id.int == 0:
        raise IdentityUnavailable("verified_user_identity_required")
    return LedgerPrincipal(user_id=user_id, issuer=issuer, audience=audience)


def research_only_grant_has_ledger_access():
    """Existing OAuth and REST research grants never imply ledger access."""
    return False
