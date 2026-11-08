"""Typed failures for metric selection stages."""


class MetricSelectionError(Exception):
    """Base class for failures that callers may handle explicitly."""


class CatalogError(MetricSelectionError):
    pass


class ConfigurationError(MetricSelectionError):
    pass


class RetrievalError(MetricSelectionError):
    pass


class EmptyCandidateError(RetrievalError):
    pass


class EmbeddingProviderError(RetrievalError):
    pass


class LLMProviderError(MetricSelectionError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class OutputParseError(LLMProviderError):
    pass


class OutputValidationError(MetricSelectionError):
    pass
