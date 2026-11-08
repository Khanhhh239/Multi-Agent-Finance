"""Reproduce PLAN_07 technical checks and public synthetic evidence."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'agent3_tax_compliance'
OUT = ROOT / 'docs/agent3/plans/evidence/plan07'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tests/planning'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def main():
    from src.planning.contracts import RulePlan, PlanningContext, RuleSet, CapabilityProfile
    from src.planning.catalog import load_catalog
    from src.planning.service import implementation_sha, plan
    from src.legal_registry.registry import LegalRegistry
    from src.taxonomy.service import Taxonomy
    import test_planning
    results = []
    for suite in ('contracts', 'ingestion', 'ocr', 'extraction_v1', 'quality', 'review', 'planning'):
        tests = unittest.TestLoader().discover(str(APP / 'tests' / suite))
        result = unittest.TextTestRunner(verbosity=1).run(tests)
        results.append(dict(suite=suite, tests=result.testsRun, failures=len(result.failures),
                            errors=len(result.errors), skipped=len(result.skipped)))
    for model in (RulePlan, PlanningContext, RuleSet, CapabilityProfile, LegalRegistry, Taxonomy):
        write(APP / 'contracts/planning-v1' / (model.__name__ + '.schema.json'), model.model_json_schema())
    fixture = test_planning.PlanningTests('test_eligible_is_plan_only_with_all_pins_and_no_engine')
    fixture.setUp()
    synthetic = fixture.evaluate()
    RulePlan.model_validate_json(synthetic.model_dump_json())
    write(OUT / 'synthetic_rule_plan.json', synthetic.model_dump(mode='json'))
    rules, legal, taxonomy = load_catalog()
    draft = plan(fixture.record, fixture.q, fixture.master, rules, legal, fixture.profile,
                 taxonomy, fixture.context, created_at=test_planning.STAMP['created_at'])
    write(OUT / 'draft_catalog_plan.json', draft.model_dump(mode='json'))
    report = dict(scope='PLAN_07 technical only; synthetic fixtures, not legal or accuracy acceptance',
        checked_on='2026-10-14', command='agent3_tax_compliance/.venv/Scripts/python.exe scripts/validate_plan07.py',
        implementation_sha256=implementation_sha(), suites=results,
        total_tests=sum(r['tests'] for r in results),
        passed=all(not r['failures'] and not r['errors'] for r in results),
        engine_calls=0, production_rules_publication=sorted({v.publication for f in rules.families for v in f.versions}),
        legal_documents=len(legal.documents), taxonomy_mappings=len(taxonomy.mappings),
        pending=['Business approval of rule metadata and exception/transitional policies',
                 'Reviewed real goods/services taxonomy mappings', 'PLAN_05/06 real-data acceptance',
                 'Signature verification and complete legal amendment review'])
    write(OUT / 'validation_summary.json', report)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
