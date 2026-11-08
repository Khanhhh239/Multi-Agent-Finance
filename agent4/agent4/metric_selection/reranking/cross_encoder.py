from typing import Protocol, runtime_checkable

from ..catalog.document_builder import MetricDocument


@runtime_checkable
class CrossEncoder(Protocol):
    @property
    def model_id(self) -> str: ...

    def score(self, question: str, documents: list[MetricDocument]) -> list[float]: ...
