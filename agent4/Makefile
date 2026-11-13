PYTHON ?= python

PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff
EVAL_RUNNER := $(PYTHON) vals/run_eval.py

EVAL_DATASET ?= data/eval/contract_benchmark_questions.jsonl
EVAL_CONFIG ?= config/selection.yaml
EVAL_MODE ?= e2e
EVAL_SPLIT ?= dev
CHECK_PATHS ?= agent4 tests scripts vals

.DEFAULT_GOAL := help

.PHONY: help install-dev format format-check lint typecheck \
	test test-core test-selection test-warehouse test-planning test-sql test-answer \
	test-security test-benchmark test-mpx10 verify ci eval-validate eval demo

help:
	@echo "  make demo              Start the governed synthetic-data demo on port 8000"
	@echo "Codex verification commands"
	@echo "  make install-dev       Install the package with development tools"
	@echo "  make format            Format Python sources and tests"
	@echo "  make format-check      Check formatting without changing files"
	@echo "  make lint              Run Ruff lint checks"
	@echo "  make typecheck         Run the configured compile-time check"
	@echo "  make test              Run the complete test suite"
	@echo "  make test-core         Run M0 contract tests"
	@echo "  make test-selection    Run M1 contract tests"
	@echo "  make test-warehouse    Run catalog SQL against the configured DuckDB read-only"
	@echo "  make test-mpx10        Run M0/M1 contracts and verify the MPX10 v3 references"
	@echo "  make test-planning     Run M2 contract tests"
	@echo "  make test-sql          Run M3 contract tests"
	@echo "  make test-answer       Run M4.1 contract tests"
	@echo "  make test-security     Run the security suite"
	@echo "  make test-benchmark    Run benchmark-runner tests"
	@echo "  make verify            Run format, lint, compile and full tests"
	@echo "  make eval-validate     Validate eval data only; not a quality eval"
	@echo "  make eval ...          Run a real development evaluation"
	@echo ""
	@echo "Evaluation example:"
	@echo "  make eval ADAPTER=package.module:predict MODEL_VERSION=model:rev \\"
	@echo "    PROMPT_VERSION=prompt-v1 OUTPUT_DIR=reports/eval/run-name"
	@echo ""
	@echo "Focused static checks:"
	@echo "  make lint CHECK_PATHS='agent4/core tests/contracts/test_intake_auth_catalog.py'"

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

format:
	$(RUFF) format $(CHECK_PATHS)

format-check:
	$(RUFF) format --check $(CHECK_PATHS)

lint:
	$(RUFF) check $(CHECK_PATHS)

# No static type checker is configured yet; preserve the existing compile-time gate.
typecheck:
	$(PYTHON) -m compileall -q agent4 scripts vals

test:
	$(PYTEST) -q tests

test-core:
	$(PYTEST) -q tests/contracts/test_intake_auth_catalog.py

test-selection:
	$(PYTEST) -q \
		tests/contracts/test_cache_governance.py \
		tests/contracts/test_metric_selection_e0.py \
		tests/contracts/test_retrieval_and_fewshot.py \
		tests/contracts/test_selection_and_metric_validation.py \
		tests/contracts/test_metric_selection_recovery.py

test-warehouse:
	$(PYTHON) -m scripts.check_warehouse

test-mpx10: test-core test-selection
	$(PYTHON) -m scripts.check_mpx10

test-planning:
	$(PYTEST) -q tests/contracts/test_planning_and_plan_validation.py tests/contracts/test_clarification_mode.py

test-sql:
	$(PYTEST) -q tests/contracts/test_compiler_safety_execution.py

test-answer:
	$(PYTEST) -q tests/contracts/test_result_answer_response.py tests/contracts/test_evidence_preview.py tests/contracts/test_governed_pipeline.py

test-security:
	$(PYTEST) -q tests/security

test-benchmark:
	$(PYTEST) -q tests/benchmark

verify: format-check lint typecheck test

ci: verify

# Dataset/schema validation is intentionally separate from behavioral evaluation.
eval-validate:
	$(EVAL_RUNNER) --dataset "$(EVAL_DATASET)" --split "$(EVAL_SPLIT)" --validate-only

# Required variables:
#   MODEL_VERSION, PROMPT_VERSION, OUTPUT_DIR
#   exactly one of ADAPTER or PREDICTIONS
# Optional variables:
#   BASELINE, THRESHOLDS, EVAL_EXTRA
eval:
	@if [ -z "$(MODEL_VERSION)" ]; then echo "MODEL_VERSION is required" >&2; exit 2; fi
	@if [ -z "$(PROMPT_VERSION)" ]; then echo "PROMPT_VERSION is required" >&2; exit 2; fi
	@if [ -z "$(OUTPUT_DIR)" ]; then echo "OUTPUT_DIR is required" >&2; exit 2; fi
	@if [ -z "$(ADAPTER)$(PREDICTIONS)" ]; then echo "Set ADAPTER or PREDICTIONS" >&2; exit 2; fi
	@if [ -n "$(ADAPTER)" ] && [ -n "$(PREDICTIONS)" ]; then echo "Set only one of ADAPTER or PREDICTIONS" >&2; exit 2; fi
	$(EVAL_RUNNER) \
		--dataset "$(EVAL_DATASET)" \
		--config "$(EVAL_CONFIG)" \
		--mode "$(EVAL_MODE)" \
		--split "$(EVAL_SPLIT)" \
		$(if $(strip $(ADAPTER)),--adapter "$(ADAPTER)",--predictions "$(PREDICTIONS)") \
		--model-version "$(MODEL_VERSION)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--output-dir "$(OUTPUT_DIR)" \
		$(if $(strip $(BASELINE)),--baseline "$(BASELINE)") \
		$(if $(strip $(THRESHOLDS)),--thresholds "$(THRESHOLDS)") $(EVAL_EXTRA)


demo:
	AGENT4_DEMO_MODE=1 $(PYTHON) -m uvicorn agent4.api:create_demo_app --factory --host 0.0.0.0 --port 8000
