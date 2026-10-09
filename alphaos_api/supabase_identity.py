"""Server-side Supabase user-token verifier for a future ledger boundary.

No API/MCP routes invoke this verifier yet. It intentionally uses Supabase
Auth's server-side get_user validation instead of trusting decoded JWT claims.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID
import os

from .identity_foundation import (
    IdentityUnavailable, LedgerPrincipal, require_ledger_principal,
)


@dataclass(frozen=True)
class SupabaseIdentityConfig:
    url: str
    publishable_key: str


def identity_config(env=None):
    env = os.environ if env is None else env
    url = str(env.get("SUPABASE_URL", "")).rstrip("/")
    key = str(env.get("SUPABASE_ANON_KEY", "")).strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path
            or not key):
        raise IdentityUnavailable("identity_provider_not_configured")
    return SupabaseIdentityConfig(url, key)


def verify_supabase_access_token(token, *, config=None, client_factory=None):
    """Verify the caller's access token with Supabase Auth, not local claims.

    The public anon/publishable key is used solely to reach Auth. No service
    role key, shared research token, user-supplied UUID, or unverified JWT
    payload is accepted. A future route must extract its own bearer credential
    and must never accept a caller-supplied 'verified' flag.
    """
    if not isinstance(token, str) or not token or len(token) > 16384:
        raise IdentityUnavailable("verified_user_identity_required")
    cfg = config if config is not None else identity_config()
    try:
        if client_factory is None:
            from supabase import create_client
            client_factory = create_client
        client = client_factory(cfg.url, cfg.publishable_key)
        response = client.auth.get_user(token)
        user = getattr(response, "user", None)
        if user is None:
            raise IdentityUnavailable("verified_user_identity_required")
        # The Auth service verifies the token and resolves the authenticated
        # user. This is not an offline JWT signature/claims verification path.
        subject = getattr(user, "id", None)
        principal = require_ledger_principal(
            verified_subject=subject, issuer=cfg.url + "/auth/v1",
            audience="authenticated", verified=True)
        return principal
    except IdentityUnavailable:
        raise
    except Exception:
        # Do not leak Auth response bodies, credentials, or network errors.
        raise IdentityUnavailable("verified_user_identity_required") from None
