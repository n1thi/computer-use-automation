from __future__ import annotations

from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel

from src.artifact.models import ActionType, Target


class PolicyDisposition(str, Enum):
    ALLOW = "allow"
    ESCALATE = "escalate"
    BLOCK = "block"


class PolicyDecision(BaseModel):
    disposition: PolicyDisposition
    reason: str


class ExecutionPolicy:
    """Deterministic guardrails applied outside the LLM and artifact."""

    DEFAULT_RISKY_TARGET_TERMS = {
        "create account",
        "delete",
        "transfer funds",
        "submit payment",
        "confirm purchase",
        "final approval",
    }

    def __init__(
        self,
        *,
        allowed_origins: set[str],
        allowed_actions: set[ActionType] | None = None,
        risky_target_terms: set[str] | None = None,
    ) -> None:
        if not allowed_origins:
            raise ValueError("ExecutionPolicy requires at least one allowed origin.")

        self.allowed_origins = {
            self._origin(origin) for origin in allowed_origins
        }
        self.allowed_actions = allowed_actions or set(ActionType)
        self.risky_target_terms = {
            term.strip().casefold()
            for term in (
                risky_target_terms
                if risky_target_terms is not None
                else self.DEFAULT_RISKY_TARGET_TERMS
            )
            if term.strip()
        }

    def evaluate_navigation(self, url: str) -> PolicyDecision:
        try:
            origin = self._origin(url)
        except ValueError as exc:
            return PolicyDecision(
                disposition=PolicyDisposition.BLOCK,
                reason=str(exc),
            )

        if origin not in self.allowed_origins:
            return PolicyDecision(
                disposition=PolicyDisposition.BLOCK,
                reason=(
                    f"Navigation to origin '{origin}' is outside the explicit "
                    "execution allowlist."
                ),
            )

        return PolicyDecision(
            disposition=PolicyDisposition.ALLOW,
            reason=f"Origin '{origin}' is allowlisted.",
        )

    def evaluate_action(
        self,
        *,
        action: ActionType,
        target: Target | None,
        value: str | None,
    ) -> PolicyDecision:
        if action not in self.allowed_actions:
            return PolicyDecision(
                disposition=PolicyDisposition.BLOCK,
                reason=f"Action type '{action.value}' is not permitted by policy.",
            )

        if action == ActionType.NAVIGATE:
            if not value:
                return PolicyDecision(
                    disposition=PolicyDisposition.BLOCK,
                    reason="Navigation action has no URL.",
                )
            return self.evaluate_navigation(value)

        if action == ActionType.CLICK and target is not None:
            target_text = self._target_text(target)
            for term in self.risky_target_terms:
                if term in target_text:
                    return PolicyDecision(
                        disposition=PolicyDisposition.ESCALATE,
                        reason=(
                            f"Click target matches risky operation '{term}'. "
                            "Human control is required."
                        ),
                    )

        return PolicyDecision(
            disposition=PolicyDisposition.ALLOW,
            reason="Action is permitted by policy.",
        )

    def evaluate_current_url(self, url: str) -> PolicyDecision:
        return self.evaluate_navigation(url)

    @staticmethod
    def _target_text(target: Target) -> str:
        parts = [
            target.name,
            target.label,
            target.text,
            target.description,
        ]
        return " ".join(part for part in parts if part).casefold()

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"URL '{url}' does not contain a valid HTTP(S) origin.")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
