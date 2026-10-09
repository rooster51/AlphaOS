"""Side-effect-free configuration assessment for a proposed MCP release.

This checks presence and safe shape, not Render state, live Supabase permissions,
secret correctness, migration readiness, or deployed commit parity.
"""
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Readiness:
    ready: bool
    blockers: tuple[str, ...]

    def public(self):
        return {"ready": self.ready, "blockers": list(self.blockers),
                "checks_are_local_only": True}


def assess_readiness(env=None):
    env = os.environ if env is None else env
    blockers = []
    for key in ("ALPHAOS_API_TOKEN", "PUBLIC_API_SECRET",
                "PUBLIC_ACCOUNT_NUMBER", "SUPABASE_URL",
                "SUPABASE_SERVICE_ROLE_KEY"):
        if not str(env.get(key, "")).strip():
            blockers.append("missing_" + key.lower())
    origin = str(env.get("ALPHAOS_PUBLIC_URL", "https://alphaos.onrender.com"))
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", origin):
        blockers.append("invalid_alphaos_public_url")
    return Readiness(not blockers, tuple(blockers))
