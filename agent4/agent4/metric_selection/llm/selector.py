from __future__ import annotations

from dataclasses import dataclass

from ..errors import OutputParseError, OutputValidationError
from ..fewshot import FewshotExample, PromptBuilder
from ..schemas import MetricCandidate, MetricSelectionResult, StructuredMetricSelection
from ..validation import SelectionValidator
from .provider import LLMProvider, TokenUsage


@dataclass(frozen=True)
class LLMSelectionOutcome:
    result: MetricSelectionResult
    prompt_token_estimate: int
    usage: TokenUsage
    validation_errors: tuple[str, ...] = ()


class LLMMetricSelector:
    def __init__(
        self,
        provider: LLMProvider,
        prompt_builder: PromptBuilder,
        validator: SelectionValidator,
        max_validation_retries: int = 1,
    ) -> None:
        self.provider = provider
        self.prompt_builder = prompt_builder
        self.validator = validator
        self.max_validation_retries = max_validation_retries

    async def select(
        self,
        question: str,
        candidates: list[MetricCandidate],
        examples: list[FewshotExample],
        context: dict | None = None,
    ) -> LLMSelectionOutcome:
        feedback: str | None = None
        last_error: Exception | None = None
        token_estimate = 0
        validation_errors: list[str] = []
        for _ in range(self.max_validation_retries + 1):
            package = self.prompt_builder.build(
                question,
                candidates,
                examples,
                context,
                validation_feedback=feedback,
            )
            token_estimate = package.token_estimate
            try:
                result = await self.provider.generate_structured(
                    package.messages, StructuredMetricSelection
                )
                pipeline_result = MetricSelectionResult.model_validate(result.model_dump())
                validated = self.validator.validate(pipeline_result, candidates, context)
                return LLMSelectionOutcome(
                    validated,
                    token_estimate,
                    self.provider.last_usage,
                    tuple(validation_errors),
                )
            except (OutputParseError, OutputValidationError, ValueError) as exc:
                last_error = exc
                validation_errors.append(str(exc))
                feedback = (
                    "The previous output failed deterministic validation: "
                    f"{exc}. Return a fresh schema-conformant result using only candidate IDs."
                )
        raise OutputValidationError(
            f"No valid LLM selection after bounded retry: {last_error}"
        ) from last_error
