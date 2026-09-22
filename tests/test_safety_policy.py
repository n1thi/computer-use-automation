from src.artifact.models import ActionType, Target
from src.safety import (
    ExecutionPolicy,
    PolicyDisposition,
)


def build_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        allowed_origins={"http://127.0.0.1:8000"},
    )


def test_allowlisted_origin_is_allowed():
    decision = build_policy().evaluate_navigation(
        "http://127.0.0.1:8000/members/12345"
    )
    assert decision.disposition == PolicyDisposition.ALLOW


def test_external_origin_is_blocked():
    decision = build_policy().evaluate_navigation(
        "https://example.com/collect"
    )
    assert decision.disposition == PolicyDisposition.BLOCK


def test_create_account_click_requires_human():
    decision = build_policy().evaluate_action(
        action=ActionType.CLICK,
        target=Target(role="button", name="Create Account"),
        value=None,
    )
    assert decision.disposition == PolicyDisposition.ESCALATE


def test_normal_search_click_is_allowed():
    decision = build_policy().evaluate_action(
        action=ActionType.CLICK,
        target=Target(role="button", name="Search Member"),
        value=None,
    )
    assert decision.disposition == PolicyDisposition.ALLOW
