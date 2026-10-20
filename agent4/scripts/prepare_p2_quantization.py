"""Prepare only missing, same-family H13 weights between measured arms.

formulas not accountant-approved. No inference or label generation occurs here.
"""
import hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
NOTICE='formulas not accountant-approved; công thức chưa được kế toán duyệt (G0.7 mở).'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def main():
    selection=json.loads((ROOT/'eval/configs/selection.json').read_text(encoding='utf8'))
    chosen=selection['config']['model'];is8=chosen.startswith('qwen3:8b')
    if not is8:
        print('4B matching-family variants were prepared previously. '+NOTICE,flush=True);return
    api=httpx.Client(base_url='http://127.0.0.1:11435',timeout=180)
    def installed():return {m['name'] for m in api.get('/api/tags').json()['models']}
    q5='agent4-qwen3-8b:q5_K_M';parent='qwen3:8b-fp16';q8='qwen3:8b-q8_0'
    env=dict(os.environ,OLLAMA_HOST='127.0.0.1:11435')
    ollama=shutil.which('ollama.exe')
    if not ollama:raise SystemExit('Local Ollama CLI missing; do not substitute model families.')
    needed=[m for m in (parent,q8) if m not in installed()]
    if needed and shutil.disk_usage(ROOT).free<40*1024**3:raise SystemExit('Need40GiB free for missing8B preparation; preserve measured artifacts.')
    for model in needed:
        print('Preparing official library weight '+model+'. '+NOTICE,flush=True)
        subprocess.run([ollama,'pull',model],cwd=ROOT,env=env,check=True)
    if q5 in installed():print('Matching8B Q5 already installed. '+NOTICE);return
    # Same dedicated endpoint, no measured model jobs overlap this phase.
    for model in api.get('/api/ps').json()['models']:
        api.post('/api/generate',json={'model':model['name'],'keep_alive':0}).raise_for_status()
    response=api.post('/api/show',json={'model':parent});response.raise_for_status();body=response.json()
    modelfile=body['modelfile'];match=re.search(r'^FROM (.+)$',modelfile,re.M)
    if not match:raise SystemExit('Parent Modelfile missing FROM; keep test sealed.')
    source=Path(match.group(1).strip().strip('"'))
    if not source.is_file():raise SystemExit('Parent FP16 blob is unavailable locally.')
    quantizer=ROOT/'artifacts/llama_cpp_b11721/llama-quantize.exe'
    if not quantizer.is_file():raise SystemExit('Previously verified b11721 quantizer unavailable; do not silently replace it.')
    folder=ROOT/'artifacts/quant_8b';folder.mkdir(exist_ok=True)
    target=folder/'qwen3-8b-Q5_K_M.gguf'
    if target.exists():raise SystemExit('Unregistered Q5 output already exists; inspect its preparation log before retrying.')
    start=time.perf_counter()
    with (folder/'quantize.log').open('w',encoding='utf8') as log:
        subprocess.run([str(quantizer),str(source),str(target),'Q5_K_M','4'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    model_path=folder/'Modelfile'
    model_path.write_text(re.sub(r'^FROM .+$','FROM "'+target.as_posix()+'"',modelfile,count=1,flags=re.M),encoding='utf8')
    subprocess.run([ollama,'create',q5,'-f',str(model_path)],cwd=ROOT,env=env,check=True)
    result=api.post('/api/show',json={'model':q5});result.raise_for_status();actual=result.json()
    if actual['details'].get('quantization_level')!='Q5_K_M' or actual.get('template')!=body.get('template'):
        raise SystemExit('Registered quant/template mismatch; do not run H13.')
    tags=api.get('/api/tags').json()['models']
    evidence={'report_notice':NOTICE,'parent_model':parent,'source_blob':source.name,'source_sha256':sha(source),
        'quantizer_release':'b11721','quantizer_exe_sha256':sha(quantizer),'elapsed_seconds':time.perf_counter()-start,
        'gguf_bytes':target.stat().st_size,'gguf_sha256':sha(target),'model_digest':next(m['digest'] for m in tags if m['name']==q5),
        'details':actual['details'],'capabilities':actual.get('capabilities'),'template_matches_fp16_parent':True,
        'quality_evaluation':'Not yet run; weight preparation only, excluded from inference latency.'}
    (ROOT/'artifacts/quantization_prepare_8b_llamacpp.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(evidence,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
