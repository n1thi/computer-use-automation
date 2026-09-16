import pytest
from pydantic import ValidationError

from src.agent.models import AgentDecision
from src.artifact.models import ActionType, Target
from src.surface.models import ObservedElement, PageObservation


def test_agent_decision_accepts_structured_click():
    decision = AgentDecision(
        action=ActionType.CLICK,
        target=Target(role="button", name="Search Member"),
        reason="Search for the requested member.",
    )

    assert decision.action == ActionType.CLICK
    assert decision.target is not None
    assert decision.target.name == "Search Member"
    assert decision.done is False


def test_agent_decision_done_needs_no_action():
    decision = AgentDecision(
        reason="The review-ready checkpoint is visible.",
        done=True,
    )

    assert decision.done is True
    assert decision.action is None


def test_non_terminal_decision_requires_action():
    with pytest.raises(ValidationError):
        AgentDecision(
            reason="I should do something next.",
            done=False,
        )


def test_type_action_requires_target_and_value():
    with pytest.raises(ValidationError):
        AgentDecision(
            action=ActionType.TYPE,
            target=Target(role="textbox", name="Member ID"),
            reason="Enter the member ID.",
        )


def test_page_observation_serializes():
    observation = PageObservation(
        url="http://127.0.0.1:8000",
        title="Member Search",
        visible_text="Member Search",
        interactive_elements=[
            ObservedElement(
                index=0,
                tag="input",
                role="textbox",
                name="Member ID",
                label="Member ID",
                input_type="text",
            )
        ],
    )

    payload = observation.model_dump()

    assert payload["url"] == "http://127.0.0.1:8000"
    assert payload["interactive_elements"][0]["name"] == "Member ID"
