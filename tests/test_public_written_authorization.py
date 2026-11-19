"""Narrow Public written historical-use permission; no live AI/MCP grant."""
import pytest

from modules.data_entitlements import (
    check_data_use, enforce_data_use, DataUseDenied,
    PRIVATE_HISTORICAL_STORAGE, LOCAL_HISTORICAL_REPLAY,
    PRIVATE_CI_TESTING, AI_ASSISTED_HISTORICAL_DEBUGGING,
    AI_ANALYSIS, PUBLIC_DISPLAY, REDISTRIBUTION, COMMERCIAL_USE,
)


@pytest.mark.parametrize("context", [
    PRIVATE_HISTORICAL_STORAGE, LOCAL_HISTORICAL_REPLAY,
    PRIVATE_CI_TESTING, AI_ASSISTED_HISTORICAL_DEBUGGING,
])
def test_public_written_historical_uses_allowed(context):
    decision = check_data_use(context, "Public")
    assert decision.allowed is True
    assert decision.code == "allowed"
    assert decision.authorization_required is False


@pytest.mark.parametrize("context", [AI_ANALYSIS, PUBLIC_DISPLAY, REDISTRIBUTION, COMMERCIAL_USE])
def test_written_historical_permission_does_not_expand_other_uses(context):
    decision = check_data_use(context, "Public")
    assert decision.allowed is False
    assert decision.code == "data_use_denied"
    with pytest.raises(DataUseDenied):
        enforce_data_use(context, "Public")


def test_unknown_provider_and_unknown_context_still_fail_closed():
    assert not check_data_use(AI_ASSISTED_HISTORICAL_DEBUGGING, "Unknown").allowed
    assert not check_data_use("live_mcp_ai_analysis", "Public").allowed
