from abc import ABC, abstractmethod
from pathlib import Path


class Adapter(ABC):
    @abstractmethod
    def load(self, path: Path) -> dict:
        """Load local files as canonical tables, without scoring or network I/O."""
        raise NotImplementedError
