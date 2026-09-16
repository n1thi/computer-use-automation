__all__ = [
    "AgentDecision",
    "DecisionModel",
    "DiscoveryRunResult",
    "DiscoveryRunner",
    "DiscoveryStatus",
    "OpenAIDecisionModel",
]


def __getattr__(name: str):
    if name == "AgentDecision":
        from .models import AgentDecision

        return AgentDecision
    if name in {"DecisionModel", "OpenAIDecisionModel"}:
        from .llm_client import DecisionModel, OpenAIDecisionModel

        return DecisionModel if name == "DecisionModel" else OpenAIDecisionModel
    if name in {"DiscoveryRunResult", "DiscoveryRunner", "DiscoveryStatus"}:
        from .discovery import (
            DiscoveryRunResult,
            DiscoveryRunner,
            DiscoveryStatus,
        )

        return {
            "DiscoveryRunResult": DiscoveryRunResult,
            "DiscoveryRunner": DiscoveryRunner,
            "DiscoveryStatus": DiscoveryStatus,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
