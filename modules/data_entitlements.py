"""Provider data-use policy and entitlements.

Market-data access is not the same thing as permission to display, redistribute
or feed observations into another service. AlphaOS defaults to deny whenever a
provider's permission for a use is unknown.

The Public Individual API is documented for the account owner's personal,
non-commercial use. Its current policy therefore permits private research only.
A future licensed feed can register a broader entitlement with an explicit
authorization reference without changing API or frontend contracts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

PRIVATE_RESEARCH = "private_research"
OWNER_PRIVATE_DISPLAY = "owner_private_display"
PUBLIC_DISPLAY = "public_display"
COMMERCIAL_USE = "commercial_use"
REDISTRIBUTION = "redistribution"
AI_ANALYSIS = "ai_analysis"

USE_CONTEXTS = (
    PRIVATE_RESEARCH,
    OWNER_PRIVATE_DISPLAY,
    PUBLIC_DISPLAY,
    COMMERCIAL_USE,
    REDISTRIBUTION,
    AI_ANALYSIS,
)
UseContext = Literal[
    "private_research",
    "owner_private_display",
    "public_display",
    "commercial_use",
    "redistribution",
    "ai_analysis",
]

POLICY_VERSION = "alphaos-data-use-v1"
_AUTHORIZATION_REQUIRED = {PUBLIC_DISPLAY, COMMERCIAL_USE, REDISTRIBUTION}
_PUBLIC_TERMS = (
    "Public Individual API terms: the Developer may use Data only through the "
    "Developer's own Application for personal, non-commercial use. Third-party "
    "access, public display, commercial use and dissemination require separate "
    "authorization."
)


@dataclass(frozen=True)
class ProviderEntitlement:
    """Documented permissions for one provider.

    Unknown providers deliberately receive no permissions. A provider adapter
    must be added here with a documented basis before AlphaOS can serve its
    observations beyond authenticated private research.
    """

    provider: str
    private_research: bool = False
    owner_private_display: bool = False
    public_display: bool = False
    commercial_use: bool = False
    redistribution: bool = False
    ai_analysis: bool = False
    basis: str = "No documented entitlement; default deny."
    authorization_reference: str | None = None

    def allows(self, use_context: str) -> bool:
        return bool(getattr(self, use_context, False)) if use_context in USE_CONTEXTS else False

    def requires_authorization(self, use_context: str) -> bool:
        return use_context in _AUTHORIZATION_REQUIRED

    def as_dict(self) -> dict:
        return asdict(self)


PUBLIC_ENTITLEMENT = ProviderEntitlement(
    provider="Public",
    private_research=True,
    # A single-owner, authenticated Application is the documented personal-use
    # case. It is not a public-display or third-party entitlement.
    owner_private_display=True,
    public_display=False,
    commercial_use=False,
    redistribution=False,
    # Public does not document permission to send its observations to an AI
    # processor. Keep this false until a documented authorization exists.
    ai_analysis=False,
    basis=_PUBLIC_TERMS,
)

# Only explicitly registered providers are entitled. Do not infer permission
# from a provider name, a successful API call, or an existing cache entry.
_ENTITLEMENTS: dict[str, ProviderEntitlement] = {
    PUBLIC_ENTITLEMENT.provider: PUBLIC_ENTITLEMENT,
}


def entitlement_for(provider: str) -> ProviderEntitlement:
    return _ENTITLEMENTS.get(str(provider), ProviderEntitlement(provider=str(provider)))


@dataclass(frozen=True)
class EntitlementDecision:
    provider: str
    use_context: str
    allowed: bool
    code: str
    reason: str
    basis: str
    policy_version: str = POLICY_VERSION
    authorization_required: bool = False
    authorization_reference_present: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


class DataUseDenied(RuntimeError):
    """A safe, provider-agnostic authorization failure."""

    code = "data_use_denied"

    def __init__(self, decision: EntitlementDecision):
        self.decision = decision
        super().__init__(decision.reason)


def check_data_use(use_context: str, provider: str = "Public", *,
                   authorization_reference: str | None = None) -> EntitlementDecision:
    """Evaluate one use without touching a provider, cache or archive."""
    entitlement = entitlement_for(provider)
    if use_context not in USE_CONTEXTS:
        return EntitlementDecision(
            provider=entitlement.provider,
            use_context=str(use_context),
            allowed=False,
            code="unknown_data_use",
            reason="The requested data use is not part of the AlphaOS policy.",
            basis=entitlement.basis,
        )
    permitted = entitlement.allows(use_context)
    supplied_reference = authorization_reference or entitlement.authorization_reference
    authorized = bool(supplied_reference) if entitlement.requires_authorization(use_context) else True
    allowed = permitted and authorized
    if not permitted:
        reason = f"{entitlement.provider} does not document permission for {use_context}."
    elif not authorized:
        reason = f"{entitlement.provider} requires documented authorization for {use_context}."
    else:
        reason = f"{entitlement.provider} permits {use_context} under the recorded policy."
    return EntitlementDecision(
        provider=entitlement.provider,
        use_context=use_context,
        allowed=allowed,
        code="allowed" if allowed else "data_use_denied",
        reason=reason,
        basis=entitlement.basis,
        authorization_required=entitlement.requires_authorization(use_context),
        authorization_reference_present=bool(supplied_reference),
    )


def enforce_data_use(use_context: str, provider: str = "Public", *,
                     authorization_reference: str | None = None) -> EntitlementDecision:
    decision = check_data_use(use_context, provider, authorization_reference=authorization_reference)
    if not decision.allowed:
        raise DataUseDenied(decision)
    return decision


def archive_write_allowed(provider: str = "Public") -> EntitlementDecision:
    """Archive writes are private-research storage, not a public export."""
    return enforce_data_use(PRIVATE_RESEARCH, provider)


def export_allowed(provider: str = "Public", *,
                   authorization_reference: str | None = None) -> EntitlementDecision:
    """Exports are redistribution unless a caller documents another use."""
    return enforce_data_use(REDISTRIBUTION, provider,
                            authorization_reference=authorization_reference)


def ai_evidence_allowed(provider: str = "Public") -> EntitlementDecision:
    """AI evidence paths must be explicitly entitled, not inferred from API access."""
    return enforce_data_use(AI_ANALYSIS, provider)
