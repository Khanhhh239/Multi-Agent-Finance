"""Validate the frozen primary-source corpus and affected runtime boundaries."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
OUT=ROOT/'docs/agent3/plans/evidence/plan12/legal_corpus_20261016'
sys.path.insert(0,str(APP))


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())


def main():
    from src.explanation_v2.contracts import Corpus,Chunk,ExplanationArtifact,LLMOutput,Policy
    from src.explanation_v2.service import implementation_sha,load_config
    from src.explanation_v2.cli import inspect,probe
    from src.legal_registry.registry import load_registry
    from src.orchestration.workflow import implementation_sha as v1_sha
    from src.canonicalization.derive import sha
    suites=[]
    for name in ('explanation','planning','e2e_v1'):
        result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().discover(str(APP/'tests'/name)))
        suites.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    for model in (Corpus,Chunk,ExplanationArtifact,LLMOutput,Policy):
        write(APP/'contracts/explanation-v1'/(model.__name__+'.schema.json'),model.model_json_schema())
    policy,corpus=load_config()
    config=inspect(policy,corpus,load_registry());config['runtime']=probe(policy)
    write(OUT/'configuration_manifest.json',config)
    legacy=json.loads((ROOT/'docs/agent3/plans/evidence/plan09/release_capture_compliance_v1.json').read_text(encoding='utf-8'))
    old_hash_unchanged=v1_sha()==legacy['workflow_sha256']
    report=dict(checked_on='2026-10-16',scope='Source fidelity/retrieval date+scope contracts and existing integration; not legal accuracy',
        suites=suites,total_tests=sum(s['tests'] for s in suites),passed=all(not s['failures'] and not s['errors'] for s in suites) and config['valid'] and old_hash_unchanged,
        implementation_sha256=implementation_sha(),corpus_sha256=sha(corpus.model_dump(mode='json')),
        v1_workflow_replay_hash_unchanged=old_hash_unchanged,v1_workflow_sha256=v1_sha(),
        source_fidelity_review='CODEX_VISUAL_AGAINST_PRIMARY_PDF',independent_legal_approval=False,
        retrieval_accuracy='NOT_ESTIMATED: required-context retrieval is not a semantic ranking benchmark',
        real_model_inference='NOT_RUN',tax_rules_release='DRAFT_UNCHANGED')
    write(OUT/'validation_summary.json',report)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
