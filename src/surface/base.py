from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.artifact.models import Target


class Surface(ABC):
    """Surface-independent interface used by replay and, later, discovery."""

    @abstractmethod
    def open(self, url: str) -> None: ...

    @abstractmethod
    def click(self, target: Target, timeout_ms: int = 5000) -> None: ...

    @abstractmethod
    def type(self, target: Target, value: str, timeout_ms: int = 5000) -> None: ...

    @abstractmethod
    def select(self, target: Target, value: str, timeout_ms: int = 5000) -> None: ...

    @abstractmethod
    def read(self, target: Target, timeout_ms: int = 5000) -> str: ...

    @abstractmethod
    def screenshot(self, path: str | Path) -> str: ...

    @abstractmethod
    def is_visible(self, target: Target, timeout_ms: int = 1000) -> bool: ...

    @abstractmethod
    def wait(self, timeout_ms: int) -> None: ...

    @property
    @abstractmethod
    def current_url(self) -> str: ...

    @abstractmethod
    def close(self) -> None: ...
