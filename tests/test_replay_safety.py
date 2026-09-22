from pathlib import Path

from src.artifact.models import (
    Action,
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    CheckpointType,
    InputParameter,
    OutputParameter,
    ParameterType,
    RunStatus,
    Step,
    Target,
)
from src.handoff.base import HandoffResult
from src.replay.engine import ReplayEngine
from src.safety import ExecutionPolicy
from src.surface.base import Surface
from src.surface.models import PageObservation


class FakeSafetySurface(Surface):
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._current_url = ""
        self.created = False
        self.final_checkpoint_checks = 0
        self.delay_final_checkpoint_once = False

    def open(self, url: str) -> None:
        self._current_url = url
        self.calls.append(("open", url))

    def observe(
        self,
        max_text_chars: int = 5000,
        max_elements: int = 50,
    ) -> PageObservation:
        return PageObservation(
            url=self._current_url,
            title="Fake",
            visible_text="",
            interactive_elements=[],
        )

    def click(self, target: Target, timeout_ms: int = 5000) -> None:
        self.calls.append(("click", target.role, target.name))
        if target.name == "Create Account":
            self.created = True

    def type(
        self,
        target: Target,
        value: str,
        timeout_ms: int = 5000,
    ) -> None:
        self.calls.append(("type", target.name, value))

    def select(
        self,
        target: Target,
        value: str,
        timeout_ms: int = 5000,
    ) -> None:
        self.calls.append(("select", target.name, value))

    def read(self, target: Target, timeout_ms: int = 5000) -> str:
        return "fake"

    def screenshot(self, path: str | Path) -> str:
        return str(path)

    def is_visible(
        self,
        target: Target,
        timeout_ms: int = 1000,
    ) -> bool:
        if target.text == "CHECKPOINT: ACCOUNT_CREATED":
            self.final_checkpoint_checks += 1
            if (
                self.delay_final_checkpoint_once
                and self.final_checkpoint_checks == 1
            ):
                return False
            return self.created

        if target.text == "CHECKPOINT: READY":
            self.final_checkpoint_checks += 1
            if (
                self.delay_final_checkpoint_once
                and self.final_checkpoint_checks == 1
            ):
                return False
            return True

        return False

    def wait(self, timeout_ms: int) -> None:
        self.calls.append(("wait", timeout_ms))

    @property
    def current_url(self) -> str:
        return self._current_url

    def close(self) -> None:
        pass


class FakeHandoff:
    def __init__(self) -> None:
        self.called = False

    def handle(
        self,
        *,
        surface: Surface,
        capability_name: str,
        step: Step,
        reason: str,
    ) -> HandoffResult:
        self.called = True
        assert isinstance(surface, FakeSafetySurface)
        surface.created = True
        surface._current_url = (
            "http://127.0.0.1:8000/members/12345/subaccounts/create"
        )
        return HandoffResult(
            resumed=True,
            action_completed_by_human=True,
            evidence=["evidence/handoff/fake.jsonl"],
        )


def policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        allowed_origins={"http://127.0.0.1:8000"},
    )


def risky_artifact() -> CapabilityArtifact:
    return CapabilityArtifact(
        artifact_version="1.0",
        name="handoff_test",
        description="Test human escalation.",
        target_application="fake",
        entry_url="http://127.0.0.1:8000",
        inputs=[],
        outputs=[],
        steps=[
            Step(
                id="risky",
                action=Action(type=ActionType.CLICK),
                target=Target(
                    role="button",
                    name="Create Account",
                ),
            )
        ],
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value="CHECKPOINT: ACCOUNT_CREATED",
        ),
    )


def retry_artifact() -> CapabilityArtifact:
    return CapabilityArtifact(
        artifact_version="1.0",
        name="retry_test",
        description="Test recoverable checkpoint.",
        target_application="fake",
        entry_url="http://127.0.0.1:8000",
        inputs=[],
        outputs=[],
        steps=[],
        success_checkpoint=Checkpoint(
            type=CheckpointType.TEXT_PRESENT,
            value="CHECKPOINT: READY",
        ),
    )


def test_risky_action_escalates_without_handoff(tmp_path):
    surface = FakeSafetySurface()
    engine = ReplayEngine(
        surface,
        evidence_dir=tmp_path,
        policy=policy(),
        handoff=None,
    )

    result = engine.run(risky_artifact(), {})

    assert result.status == RunStatus.ESCALATED
    assert result.code == "HUMAN_REQUIRED"
    assert ("click", "button", "Create Account") not in surface.calls


def test_human_completes_risky_action_in_same_session(tmp_path):
    surface = FakeSafetySurface()
    handoff = FakeHandoff()
    engine = ReplayEngine(
        surface,
        evidence_dir=tmp_path,
        policy=policy(),
        handoff=handoff,
    )

    result = engine.run(risky_artifact(), {})

    assert result.status == RunStatus.SUCCESS
    assert handoff.called is True
    assert ("click", "button", "Create Account") not in surface.calls
    assert "human handoff" in (result.message or "")


def test_disallowed_entry_origin_is_blocked(tmp_path):
    artifact = retry_artifact().model_copy(
        update={"entry_url": "https://example.com"}
    )
    surface = FakeSafetySurface()
    engine = ReplayEngine(
        surface,
        evidence_dir=tmp_path,
        policy=policy(),
    )

    result = engine.run(artifact, {})

    assert result.status == RunStatus.FAILURE
    assert result.code == "POLICY_BLOCKED"
    assert not any(call[0] == "open" for call in surface.calls)


def test_checkpoint_condition_is_retried_and_recovers(tmp_path):
    surface = FakeSafetySurface()
    surface.delay_final_checkpoint_once = True

    engine = ReplayEngine(
        surface,
        evidence_dir=tmp_path,
        policy=policy(),
        checkpoint_retries=1,
        checkpoint_retry_delay_ms=1,
    )

    result = engine.run(retry_artifact(), {})

    assert result.status == RunStatus.SUCCESS
    assert "Recovered from 1 transient checkpoint condition" in (
        result.message or ""
    )
    assert ("wait", 1) in surface.calls

    logs = list(tmp_path.glob("retry_test_*.jsonl"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert '"event": "recoverable_condition"' in text
    assert '"event": "recoverable_condition_recovered"' in text
