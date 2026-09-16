from pathlib import Path
from typing import Any

from src.agent.discovery import DiscoveryRunner, DiscoveryStatus
from src.agent.models import AgentDecision
from src.artifact.models import ActionType, Checkpoint, CheckpointType, Target
from src.surface.base import Surface
from src.surface.models import ObservedElement, PageObservation


class FakeDecisionModel:
    def __init__(self, decisions: list[AgentDecision]) -> None:
        self.decisions = list(decisions)

    def decide(
        self,
        *,
        goal: str,
        inputs: dict[str, str],
        observation: PageObservation,
        history: list[dict[str, Any]],
        success_condition: str | None = None,
    ) -> AgentDecision:
        return self.decisions.pop(0)


class FakeDiscoverySurface(Surface):
    def __init__(self) -> None:
        self.state = "search"
        self.member_id = ""
        self._current_url = ""

    def open(self, url: str) -> None:
        self._current_url = url
        self.state = "search"

    def observe(
        self,
        max_text_chars: int = 5000,
        max_elements: int = 50,
    ) -> PageObservation:
        if self.state == "search":
            elements = [
                ObservedElement(
                    index=0,
                    tag="input",
                    role="textbox",
                    name="Member ID",
                    label="Member ID",
                    input_type="text",
                ),
                ObservedElement(
                    index=1,
                    tag="button",
                    role="button",
                    name="Search Member",
                    text="Search Member",
                ),
            ]
            text = "Member Search"
        elif self.state == "member":
            elements = [
                ObservedElement(
                    index=0,
                    tag="a",
                    role="link",
                    name="Open New Sub-account",
                    text="Open New Sub-account",
                )
            ]
            text = "Member Details"
        elif self.state == "form":
            elements = [
                ObservedElement(
                    index=0,
                    tag="input",
                    role="radio",
                    name="Savings",
                    label="Savings",
                    input_type="radio",
                    checked=False,
                ),
                ObservedElement(
                    index=1,
                    tag="button",
                    role="button",
                    name="Continue",
                    text="Continue",
                ),
            ]
            text = "Open Sub-account"
        else:
            elements = []
            text = "CHECKPOINT: REVIEW_READY"

        return PageObservation(
            url=self._current_url,
            title="Fake",
            visible_text=text,
            interactive_elements=elements,
        )

    def click(self, target: Target, timeout_ms: int = 5000) -> None:
        if target.name == "Search Member":
            self.state = "member"
        elif target.name == "Open New Sub-account":
            self.state = "form"
        elif target.name and target.name.casefold() == "savings":
            pass
        elif target.name == "Continue":
            self.state = "review"

    def type(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        self.member_id = value

    def select(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        pass

    def read(self, target: Target, timeout_ms: int = 5000) -> str:
        return ""

    def screenshot(self, path: str | Path) -> str:
        return str(path)

    def is_visible(self, target: Target, timeout_ms: int = 1000) -> bool:
        return (
            self.state == "review"
            and target.text == "CHECKPOINT: REVIEW_READY"
        )

    def wait(self, timeout_ms: int) -> None:
        pass

    @property
    def current_url(self) -> str:
        return self._current_url

    def close(self) -> None:
        pass


def test_discovery_executes_structured_actions_until_checkpoint(tmp_path):
    decisions = [
        AgentDecision(
            action=ActionType.TYPE,
            target=Target(role="textbox", name="Member ID"),
            value="12345",
            reason="Enter the member ID.",
        ),
        AgentDecision(
            action=ActionType.CLICK,
            target=Target(role="button", name="Search Member"),
            reason="Search for the member.",
        ),
        AgentDecision(
            action=ActionType.CLICK,
            target=Target(role="link", name="Open New Sub-account"),
            reason="Open the sub-account flow.",
        ),
        AgentDecision(
            action=ActionType.CLICK,
            target=Target(role="radio", name="Savings"),
            reason="Choose savings.",
        ),
        AgentDecision(
            action=ActionType.CLICK,
            target=Target(role="button", name="Continue"),
            reason="Continue to review.",
        ),
    ]

    runner = DiscoveryRunner(
        surface=FakeDiscoverySurface(),
        decision_model=FakeDecisionModel(decisions),
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value="CHECKPOINT: REVIEW_READY",
        ),
        evidence_dir=tmp_path,
    )

    result = runner.run(
        goal="Open a savings sub-account for member 12345.",
        inputs={
            "member_id": "12345",
            "account_type": "savings",
        },
        entry_url="http://fake",
    )

    assert result.status == DiscoveryStatus.SUCCESS
    assert result.steps_executed == 5
    assert result.log_path is not None


def test_discovery_rejects_unobserved_target(tmp_path):
    decisions = [
        AgentDecision(
            action=ActionType.CLICK,
            target=Target(role="button", name="Imaginary Button"),
            reason="Click an invented button.",
        )
    ]

    runner = DiscoveryRunner(
        surface=FakeDiscoverySurface(),
        decision_model=FakeDecisionModel(decisions),
        evidence_dir=tmp_path,
    )

    result = runner.run(
        goal="Do something.",
        inputs={},
        entry_url="http://fake",
        max_steps=1,
    )

    assert result.status == DiscoveryStatus.FAILURE
    assert "not present" in (result.message or "")
