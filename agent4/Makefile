PYTHON ?= python

.PHONY: lint typecheck test-unit test-finance test-integration test-security test-e2e eval demo test-all contracts capabilities

lint:
	ruff check agent4 tests scripts

typecheck:
	$(PYTHON) -m compileall -q agent4 scripts

test-unit:
	pytest -q tests/unit tests/text2sql/test_catalog_contracts.py tests/text2sql/test_validator.py tests/text2sql/test_compiler_security.py

test-finance:
	pytest -q tests/text2sql/test_finance.py

test-integration:
	pytest -q tests/integration tests/text2sql/test_service_api.py

test-security:
	pytest -q tests/text2sql/test_compiler_security.py tests/text2sql/test_service_api.py -k 'injection or auth or readiness or unsafe or forbidden'

test-e2e:
	pytest -q tests/text2sql/test_service_api.py

eval:
	$(PYTHON) scripts/benchmark_retrieval.py data/eval/test.jsonl --output reports/eval/retrieval_metrics.json
	$(PYTHON) scripts/benchmark_text2sql.py

demo:
	$(PYTHON) scripts/demo_text2sql.py

contracts:
	$(PYTHON) scripts/export_contracts.py

capabilities:
	$(PYTHON) scripts/generate_capability_matrix.py

test-all: lint typecheck test-unit test-finance test-integration test-security test-e2e
	pytest -q
