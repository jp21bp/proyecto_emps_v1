from abc import ABC, abstractmethod
from typing import Any

from job_discovery.collectors.models import CollectionResult


class BaseCollector(ABC):
    """Common interface implemented by all ATS collectors."""

    platform: str

    @abstractmethod
    def collect(self, board_identifier: str) -> CollectionResult:
        """Collect and normalize all available jobs from a board."""

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *args: object) -> None:
        close = getattr(self, "close", None)

        if close is not None:
            close()
