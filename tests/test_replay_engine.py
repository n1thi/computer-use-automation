from pathlib import Path

from src.artifact.models import RunStatus, Target
from src.replay.engine import ReplayEngine
from src.surface.base import Surface


class FakeSurface(Surface):
    def __init__(self, business_outcome: str | None = None) -> None:
        self.calls: list[tuple] = []
        self.business_outcome = business_outcome
        self._current_url = ""

    def open(self, url: str) -> None:
        self._current_url = url
        self.calls.append(("open", url))

    def click(self, target: Target, timeout_ms: int = 5000) -> None:
        self.calls.append(("click", target.role, target.name))

    def type(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        self.calls.append(("type", target.role, target.name, value))

    def select(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        self.calls.append(("select", target.role, target.name, value))

    def read(self, target: Target, timeout_ms: int = 5000) -> str:
        self.calls.append(("read", target.role, target.name))
        return "fake"

    def screenshot(self, path: str | Path) -> str:
        self.calls.append(("screenshot", str(path)))
        return str(path)

    def is_visible(self, target: Target, timeout_ms: int = 1000) -> bool:
        if self.business_outcome and target.text == f"OUTCOME: {self.business_outcome}":
            return True
        if target.text in {"Open Sub-account", "CHECKPOINT: REVIEW_READY"}:
            return True
        if target.role == "link" and target.name == "Open New Sub-account":
            return True
        return False

    def wait(self, timeout_ms: int) -> None:
        self.calls.append(("wait", timeout_ms))

    @property
    def current_url(self) -> str:
        return self._current_url

    def close(self) -> None:
        pass


def load_demo_artifact():
    return ReplayEngine.load_artifact("artifacts/open_sub_account_v1.json")


def test_replay_resolves_parameters_and_reaches_success():
    surface = FakeSurface()
    engine = ReplayEngine(surface)
    artifact = load_demo_artifact()

    result = engine.run(
        artifact,
        {"member_id": "12345", "account_type": "savings"},
    )

    assert result.status == RunStatus.SUCCESS
    assert result.outputs["review_status"] == "REVIEW_READY"
    assert ("type", "textbox", "Member ID", "12345") in surface.calls
    assert ("click", "radio", "savings") in surface.calls


def test_replay_returns_known_business_outcome():
    surface = FakeSurface(business_outcome="MEMBER_NOT_FOUND")
    engine = ReplayEngine(surface)
    artifact = load_demo_artifact()

    result = engine.run(
        artifact,
        {"member_id": "99999", "account_type": "savings"},
    )

    assert result.status == RunStatus.BUSINESS_OUTCOME
    assert result.code == "MEMBER_NOT_FOUND"


def test_replay_rejects_invalid_enum_input():
    surface = FakeSurface()
    engine = ReplayEngine(surface)
    artifact = load_demo_artifact()

    result = engine.run(
        artifact,
        {"member_id": "12345", "account_type": "money_market"},
    )

    assert result.status == RunStatus.FAILURE
    assert "must be one of" in (result.message or "")
