"""Replay immutable PLAN_05 evidence using its exact pinned quality source, without migrating its DBs."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.persistence.repository import digest
import src.quality
src.quality.__path__=[str(ROOT/'archive/plan06_pinned_plan05_quality')]
from src.quality.repository import QualityRepository,replay,implementation_sha
from src.quality.contracts import QualityAssessment
from src.config import Settings
from src.domain.taxpayer import AccessContext

def main():
    summary=json.loads((ROOT/'docs/agent3/plans/evidence/plan05/baseline_summary.json').read_text(encoding='utf-8'))
    validation=json.loads((ROOT/'docs/agent3/plans/evidence/plan05/validation_summary.json').read_text(encoding='utf-8'))
    assert implementation_sha()==validation['implementation_sha256']
    for file in (ROOT/'archive/plan06_pinned_plan05_quality').glob('*.py'):
        original=ROOT/'agent3_tax_compliance/src/quality'/file.name
        assert digest(file.read_bytes())==validation['source_sha256'][str(original.relative_to(ROOT))]
    for row in summary['outcomes']:
        raw=(ROOT/row['artifact_path']).read_bytes();assert digest(raw)==row['artifact_sha256']
        assessment=QualityAssessment.model_validate_json(raw)
        repo=QualityRepository(Settings(database_path=ROOT/'data invoice/plan05_local'/(row['cohort']+'.sqlite3')))
        ctx=AccessContext(actor_id='historical-replay-read-only',tenant_id=assessment.tenant_id,taxpayer_ids=frozenset({assessment.taxpayer_id}))
        assert replay(repo.inputs(ctx,assessment.taxpayer_id,assessment.assessment_id),assessment)==assessment
    print('PASS: 15 historical PLAN_05 assessments replayed with exact pinned source; no migration or OCR execution.')
if __name__=='__main__':main()
