from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.artifact.models import Target
from src.surface.models import PageObservation


class Surface(ABC):
    """Surface-independent interface used by replay and discovery."""

    @abstractmethod
    def open(self, url: str) -> None:
        pass

    @abstractmethod
    def observe(
        self,
        max_text_chars: int = 5000,
        max_elements: int = 50,
    ) -> PageObservation:
        pass

    @abstractmethod
    def click(self, target: Target, timeout_ms: int = 5000) -> None:
        pass

    @abstractmethod
    def type(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        pass

    @abstractmethod
    def select(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        pass

    @abstractmethod
    def read(self, target: Target, timeout_ms: int = 5000) -> str:
        pass

    @abstractmethod
    def screenshot(self, path: str | Path) -> str:
        pass

    @abstractmethod
    def is_visible(self, target: Target, timeout_ms: int = 1000) -> bool:
        pass

    @abstractmethod
    def wait(self, timeout_ms: int) -> None:
        pass

    @property
    @abstractmethod
    def current_url(self) -> str:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
