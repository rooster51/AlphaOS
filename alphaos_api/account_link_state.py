"""Isolated, fail-closed account-linking state machine; NOT an HTTP endpoint.

The caller MUST first authenticate the MCP OAuth grant server-side and verify
the browser's Supabase access token with Supabase Auth. Never construct a grant
identity from browser-supplied client IDs, token claims or the legacy 'owner'
subject. This store does not elevate existing research scopes.
"""
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from time import monotonic
from uuid import UUID

from .identity_foundation import LedgerPrincipal


class LinkDenied(PermissionError):
    pass


@dataclass(frozen=True)
class VerifiedGrant:
    """Only trusted OAuth server code may construct this after grant validation."""
    grant_fingerprint: str
    client_id: str

    def __post_init__(self):
        if (not isinstance(self.grant_fingerprint, str)
                or len(self.grant_fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in self.grant_fingerprint)
                or not isinstance(self.client_id, str) or not self.client_id):
            raise LinkDenied("verified_grant_required")


@dataclass(frozen=True)
class LinkedIdentity:
    grant_fingerprint: str
    client_id: str
    user_id: UUID
    issuer: str
    audience: str
    expires_at: float


class AccountLinkStore:
    """Process-local prototype: restart clears all pending and linked grants."""

    def __init__(self, *, clock=monotonic, pending_ttl=300, link_ttl=900):
        if not 0 < pending_ttl <= 300 or not 0 < link_ttl <= 900:
            raise ValueError("invalid_link_ttl")
        self.clock = clock
        self.pending_ttl = pending_ttl
        self.link_ttl = link_ttl
        self._pending = {}
        self._linked = {}

    @staticmethod
    def _digest(ticket):
        return sha256(ticket.encode("utf-8")).hexdigest()

    def begin(self, grant: VerifiedGrant):
        """Call only after OAuth access token validation, never from raw input."""
        if not isinstance(grant, VerifiedGrant):
            raise LinkDenied("verified_grant_required")
        ticket = token_urlsafe(32)
        self._pending[self._digest(ticket)] = (
            grant, self.clock() + self.pending_ttl)
        return ticket

    def approve(self, ticket: str, grant: VerifiedGrant,
                principal: LedgerPrincipal, *, explicit_consent: bool):
        """Consume a one-time ticket bound to the SAME verified OAuth grant."""
        if not isinstance(ticket, str) or len(ticket) > 256:
            raise LinkDenied("invalid_link_request")
        entry = self._pending.pop(self._digest(ticket), None)
        if (entry is None or not isinstance(grant, VerifiedGrant)
                or not isinstance(principal, LedgerPrincipal)
                or not explicit_consent):
            raise LinkDenied("link_denied")
        original, expiry = entry
        if expiry <= self.clock() or original != grant:
            raise LinkDenied("link_denied")
        if (not isinstance(principal.user_id, UUID)
                or principal.user_id.int == 0 or not principal.issuer
                or not principal.audience):
            raise LinkDenied("verified_user_required")
        link = LinkedIdentity(grant.grant_fingerprint, grant.client_id,
            principal.user_id, principal.issuer, principal.audience,
            self.clock() + self.link_ttl)
        self._linked[grant.grant_fingerprint] = link
        return link

    def resolve(self, grant: VerifiedGrant):
        if not isinstance(grant, VerifiedGrant):
            raise LinkDenied("verified_grant_required")
        link = self._linked.get(grant.grant_fingerprint)
        if link is None or link.client_id != grant.client_id:
            raise LinkDenied("account_link_required")
        if link.expires_at <= self.clock():
            self._linked.pop(grant.grant_fingerprint, None)
            raise LinkDenied("account_link_expired")
        return link

    def revoke(self, grant: VerifiedGrant):
        if not isinstance(grant, VerifiedGrant):
            raise LinkDenied("verified_grant_required")
        self._linked.pop(grant.grant_fingerprint, None)
        self._pending = {key: value for key, value in self._pending.items()
                         if value[0] != grant}
