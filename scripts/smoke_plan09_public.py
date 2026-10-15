"""Public pilot PDF through the configured OCR/router in a temporary DB; no tax-accuracy claim."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/e2e_v1'))
import test_compliance as fixtures
from src.ingestion.service import IngestionService
from src.ingestion.upload import StagedUpload
from src.adapters.ocr.bridge import OCRBridge,config_key
from src.canonicalization.derive import sha


def main():
    case=ROOT/'data invoice/real_invoice_pilot_v1/cases/cyber_construction-p69.pdf'
    output=ROOT/'docs/agent3/plans/evidence/plan09/public_smoke.json'
    if not case.is_file():
        report=dict(status='PENDING',reason='Optional public pilot PDF is not present on this machine',legal_accuracy='NOT_EVALUATED')
    else:
        fixture=fixtures.ComplianceTests('test_default_catalog_no_false_tax_pass_and_capture_export_works');fixture.setUp()
        try:
            workflow=fixture.workflow;service=IngestionService(fixture.settings);raw=case.read_bytes()
            start=time.perf_counter()
            with StagedUpload(fixture.settings) as staged:
                staged.write(raw);view=service.accept_staged(fixture.ctx,fixture.payer,1,'plan09-public-native',staged,'application/pdf',case.name)
            ingestion=service.work_one(fixture.ctx,fixture.payer,view.ingestion_id)
            if ingestion.status!='SUCCEEDED':raise ValueError('Native ingestion did not complete')
            bridge=OCRBridge(fixture.settings)
            config=bridge.config
            runtime=bridge.client.inventory()['runtime_sha256']
            bridge.work_one(fixture.ctx,fixture.payer,view.ingestion_id)
            artifact=workflow.quality.extraction.work(fixture.ctx,fixture.payer,view.ingestion_id,config_key(config,runtime))
            if artifact.record is None:raise ValueError('Document boundary requires review before a CFR can be evaluated')
            workflow.quality.work(fixture.ctx,fixture.payer,artifact.artifact_id)
            from src.orchestration.contracts import EvaluationCommand
            result=workflow.work(fixture.ctx,fixture.payer,artifact.record.record_id,EvaluationCommand(expected_record_revision=1),'plan09-public-evaluation')
            workflow.replay(fixture.ctx,fixture.payer,result.evaluation_id)
            assert result.report.aggregate.verdict not in ('PASS','PASS_WITHIN_SCOPE','FAIL')
            report=dict(status='PASS_TECHNICAL_SMOKE',case_id=case.stem,source_sha256=sha_raw(raw),documents=1,pages=1,
                route='PUBLIC_PDF_PRODUCTION_ROUTER_AND_CONFIGURED_OCR',ocr_model_id=config.model_id,
                elapsed_seconds=time.perf_counter()-start,
                result=result.status,coverage=result.report.aggregate.coverage,verdict=result.report.aggregate.verdict,
                evaluated_units=result.report.aggregate.counts.evaluated,replay_verified=True,
                legal_accuracy='NOT_EVALUATED_NO_APPROVED_RULES_OR_EXPECTED_LEGAL_LABELS',
                extraction_accuracy='NOT_EVALUATED_THIS_SMOKE',independent_label_review=False)
        finally:fixture.doCleanups()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=True,indent=2))


def sha_raw(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


if __name__=='__main__':main()
