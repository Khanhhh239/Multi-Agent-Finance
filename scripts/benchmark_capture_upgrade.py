"""Real local recognizer and optional Ollama smoke; selected DEV, never holdout."""
import hashlib,json,sys,time,urllib.request
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
OUT=APP/'data/capture_upgrade';OUT.mkdir(parents=True,exist_ok=True)

def main():
    from src.adapters.ocr.worker_client import WorkerClient
    from src.adapters.ocr.protocol import OCRConfig,OCRBridgeRequest
    from src.recovery.field_reads import text_read
    source=APP/'data/field_coverage_round3/software_kct-p1-parties_buyer_name-1.png'
    label=json.loads((ROOT/'data invoice/real_invoice_pilot_v1/labels.json').read_bytes())['software_kct-p1']['fields']['parties.buyer.name']
    import unicodedata
    normalize=lambda t:' '.join(unicodedata.normalize('NFC',str(t)).split())
    rows=[]
    for scale in (1,2):
        path=OUT/f'dev-name-{scale}x.png'
        with Image.open(source) as im:
            with im.resize((im.width*scale,im.height*scale),Image.Resampling.LANCZOS) as scaled:scaled.save(path)
            w,h=im.width*scale,im.height*scale
        client=WorkerClient(model_id='vietocr_region_v1');runtime=client.inventory()['runtime_sha256']
        config=OCRConfig(version='capture-upgrade-dev-v1',model_id='vietocr_region_v1',timeout_seconds=45,memory_mb=3072,max_attempts=1)
        req=OCRBridgeRequest(config_version=config.version,creator='benchmark',stage='ocr',request_id='dev-region-'+str(scale),source_id='dev',document_id='dev',page_id='dev',page_index=0,
            image_hash=hashlib.sha256(path.read_bytes()).hexdigest(),image_path=str(path.resolve()),image_width=w,image_height=h,
            model_config_version=config.version,runtime_sha256=runtime,model_id=config.model_id,timeout_seconds=config.timeout_seconds)
        started=time.perf_counter()
        try:
            response=client.run_batch([req],config)[0];(OUT/f'ocr-{scale}.private.json').write_bytes(response.model_dump_json().encode())
            value=text_read('parties.buyer.name',[response.result.document_text_raw])
            rows.append(dict(scale=scale,labeled=1,exact=int(normalize(value)==normalize(label)),elapsed_seconds=time.perf_counter()-started,
                load_ms=response.result.load_time_ms,inference_ms=response.result.inference_time_ms,runtime_sha256=runtime,status='COMPLETE'))
        except Exception as exc:rows.append(dict(scale=scale,status='FAILED',error_type=type(exc).__name__,elapsed_seconds=time.perf_counter()-started))
    llm={'status':'UNAVAILABLE','attempted':False}
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as response:tags=json.load(response)
        if any(m['name']=='qwen3:8b' for m in tags.get('models',[])):
            from src.explanation_v2.contracts import Policy,Context,Fact
            from src.explanation_v2.llm import provider_for
            from src.explanation_v2.natural import validate_draft
            policy=Policy.model_validate_json((APP/'configs/explanation/policy.local.json').read_bytes())
            context=Context(evaluation_id='smoke',record_revision=1,record_sha256='a'*64,excerpts=(),facts=(
                Fact(fact_id='summary',variants=('Đã đọc 3 trường; chưa có trường được xác nhận.',),refs=('evaluation:smoke',)),
                Fact(fact_id='scope',variants=('Chỉ giải thích dữ liệu; chưa kiểm tra thuế.',),refs=('evaluation:smoke',)),
                Fact(fact_id='coverage',variants=('Chưa đọc được dòng hàng.',),refs=('evaluation:smoke',)),
                Fact(fact_id='notice-data',variants=('Bảng hàng chưa đủ; chưa chứng minh hóa đơn hợp lệ.',),refs=('evaluation:smoke',)),
                Fact(fact_id='action-data',variants=('Bạn cần chọn Bổ sung dòng hàng, chọn vùng nguồn, đối chiếu rồi lưu.',),refs=('evaluation:smoke',))))
            llm={'status':'RUNNING','attempted':True};started=time.perf_counter()
            raw=provider_for(policy).generate(context,policy)
            (OUT/'qwen-raw.private.json').write_text(raw,encoding='utf-8')
            draft=validate_draft(raw,context)
            (OUT/'qwen.private.json').write_bytes(draft.model_dump_json(indent=2).encode())
            llm=dict(status='STRUCTURAL_GUARDS_PASSED',attempted=True,elapsed_seconds=time.perf_counter()-started,model=policy.model,
                model_revision=policy.model_revision,semantic_approval=False)
    except Exception as exc:
        reasons=('Unsupported number in natural explanation','Internal identifiers are not user-facing narrative',
            'Unsupported conclusion in natural explanation','Unsupported legal locator','Scope, warning or next action omitted',
            'Unknown or duplicate natural explanation references','Data-only explanation cannot assert a tax/payment conclusion')
        llm.update(status='FALLBACK_REQUIRED',error_type=type(exc).__name__,reason=str(exc) if str(exc) in reasons else 'MODEL_OR_SCHEMA_GUARD')
    report=dict(scope='One previously used DEV crop: resize-only ablation, no padding experiment or general accuracy claim. Local Qwen synthetic data-only smoke, no real invoice sent.',
        ocr=rows,llm=llm,default_profile_changed=False,quality_release_approved=False)
    (OUT/'real_runtime.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
