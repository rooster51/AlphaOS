"""Shared Public authentication helpers; independent of Streamlit."""
from typing import Any

def _select_account(accounts: list[Any], preferred: str | None) -> Any:
    if preferred:
        preferred = preferred.strip()
        match = next(
            (
                account
                for account in accounts
                if str(getattr(account, "account_id", "")).strip() == preferred
                or str(getattr(account, "account_number", "")).strip() == preferred
            ),
            None,
        )
        if match is None:
            raise RuntimeError("PUBLIC_ACCOUNT_NUMBER is not available for this key.")
        return match

    scored = sorted(
        accounts,
        key=_account_selection_score,
        reverse=True,
    )
    return scored[0]


def _account_field(account: Any, field: str) -> str:
    value = getattr(account, field, "")
    value = getattr(value, "value", value)
    return str(value or "")


def _account_search_text(account: Any) -> str:
    fields = (
        "account_type",
        "account_sub_type",
        "account_name",
        "nickname",
        "name",
        "display_name",
    )
    return " ".join(_account_field(account, field) for field in fields).casefold()


def _account_selection_score(account: Any) -> int:
    text = _account_search_text(account)
    score = 0
    if "broker" in text:
        score += 50
    if "individual" in text or "cash" in text or "margin" in text:
        score += 20
    if "ira" in text or "retirement" in text or "roth" in text or "traditional" in text:
        score -= 100
    return score


