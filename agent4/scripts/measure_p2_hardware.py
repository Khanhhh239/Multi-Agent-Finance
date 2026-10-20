"""Small TRAIN-only controlled ctx probes, never held-out quality evidence."""
import json,subprocess,sys,time
from dataclasses import asdict
from pathlib import Path
import httpx,numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent4.agent.pipeline import PipelineConfig


def main():
    api=httpx.Client(base_url='http://127.0.0.1:11435',timeout=180)
    profiles=[('4B_ctx8192','qwen3:4b-instruct-2507-q4_K_M',8192),('8B_ctx4096','qwen3:8b',4096),('8B_ctx8192','qwen3:8b',8192)]
    all_results=[]
    for label,model,ctx in profiles:
        for m in api.get('/api/ps').json()['models']:api.post('/api/generate',json={'model':m['name'],'keep_alive':0}).raise_for_status()
        start=time.perf_counter()
        api.post('/api/generate',json={'model':model,'stream':False,'keep_alive':'30m','options':{'num_ctx':ctx}}).raise_for_status()
        load_ms=(time.perf_counter()-start)*1000;runtime=api.get('/api/ps').json()
        cfg=asdict(PipelineConfig(name='hardware_'+label,model=model,num_ctx=ctx,hints=True,k=8,output_mode='schema',verifier=True))
        config=ROOT/'eval/configs'/('hardware_'+label+'.yaml');config.write_text(json.dumps(cfg,indent=2),encoding='utf8')
        out=ROOT/'eval/results'/('hardware_'+label)
        if out.exists():raise SystemExit('Hardware output already exists; preserve observations, choose an explicitly new probe name.')
        subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-X','utf8','-m','eval.run','--split','train','--suite','e1,e7,multi,why','--n','10',
                        '--config',str(config),'--out',str(out)],cwd=ROOT,check=True)
        summary=json.loads((out/'summary.json').read_text(encoding='utf8'));gpu=json.loads((out/'gpu.json').read_text(encoding='utf8'))
        rows=[json.loads(l) for l in (out/'results.jsonl').read_text(encoding='utf8').splitlines()]
        calls=[m for r in rows for m in r.get('llm',[])];eval_ns=sum(m.get('eval_duration') or 0 for m in calls)
        prefills=[m['prompt_eval_duration']/1e6 for m in calls if m.get('prompt_eval_duration')]
        result={'report_notice':'formulas not accountant-approved','profile':label,'config':cfg,'n_train':summary['n'],'load_ms':load_ms,
                'runtime_ps':runtime,'gpu':{k:v for k,v in gpu.items() if k!='samples'},'latency':summary['latency_model_cases'],
                'prefill_median_ms':float(np.median(prefills)) if prefills else None,
                'generation_tok_s':sum(m.get('usage',{}).get('eval_tokens',0) for m in calls)/(eval_ns/1e9) if eval_ns else None,
                'tool_accuracy_train':summary['by_suite'].get('e1',{}).get('tool_correct'),
                'train_suite_metrics':summary['by_suite'],'server_runtime_events':summary.get('server_runtime_events'),
                'unknown_usage_calls':summary['llm_usage_unknown_calls'],'not_normal_stops':sum(m.get('done_reason') not in ('stop',None) for m in calls),
                'incomplete':summary['excluded_or_incomplete'],
                'note':'Same TRAIN subset:10 E1 +10 E7 conversations +10 multi +10 why; narrow k8 schema, hints on, think off, static3. Single-question latency n30 excludes whole-conversation durations. Warm E2E includes first prompt prefill, empty weight preload separate. Total GPU peak includes display/other workloads. Small stability stress probe, not validation accuracy or a long soak.'}
        all_results.append(result)
        path=ROOT/'docs/5_handoff/measurements/p2_hardware_train.json'
        path.write_text(json.dumps(all_results,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    path=ROOT/'docs/4_ai_engineering/06_toi_uu_trien_khai.md'
    old=path.read_text(encoding='utf8');marker='## 8. Bảng ghi số đo'
    if marker not in old:raise SystemExit('Hardware table heading missing; preserve the document for inspection.')
    lines=['## 8. Bảng ghi số đo — P2 thử nghiệm','','**formulas not accountant-approved** — công thức chưa được kế toán duyệt (G0.7 mở).','',
           '| Cấu hình | VRAM đỉnh lấy mẫu (MiB) | Prefill median (ms/call) | tok/s sinh | p50 / p95 E2E (ms) | TSA | Ghi chú |',
           '|---|---:|---:|---:|---:|---:|---|']
    labels=['4B Q4 · ctx8192 · KV q8_0','8B Q4 · ctx4096 · KV q8_0','8B Q4 · ctx8192 · KV q8_0']
    def number(value):return 'chưa đo' if value is None else f'{value:.1f}'
    for label,r in zip(labels,all_results):
        lat=r['latency'];tsa=r['tool_accuracy_train'];g=r['gpu'];events=r.get('server_runtime_events') or {}
        note=f'TRAIN n={r["n_train"]}; E1 n={tsa["n"]}; latency n={lat["n"]}; API errors={r["unknown_usage_calls"]}; length stops={r["not_normal_stops"]}; context shifts={events.get("context_shift_events","chưa đo")}'
        lines.append(f'| {label} | {g["total_device_peak_mib"]} | {number(r["prefill_median_ms"])} | {number(r["generation_tok_s"])} | {number(lat["p50_ms"])} / {number(lat["p95_ms"])} | {tsa["estimate"]:.3f} | {note} |')
    lines.append('| 8B think=on · đợi H4 | chưa đo | chưa đo | chưa đo | chưa đo | chưa đo | Không suy diễn số đo |')
    lines+=['','Nguồn: `docs/5_handoff/measurements/p2_hardware_train.json`. Cùng mẫu TRAIN:10 E1,10 hội thoại E7,10 câu nhiều chỉ số,10 câu vì sao. k8, schema, hints bật, static3, think tắt. E2E n30 loại thời gian toàn hội thoại E7; n thực tế ghi từng dòng. Cold preload đo riêng trong JSON.','',
            'VRAM là đỉnh quan sát toàn GPU (gồm màn hình/tác vụ khác), lấy mẫu khoảng1 giây; không phải allocator peak. Máy dùng chung, chưa có kiểm soát tải nền hoặc long soak. TSA ở đây là TRAIN, không thay thế kết quả val/test hay chứng nhận G1. Chọn cấu hình8B ổn định theo API/context/truncation thực đo và xem độ đúng riêng; không suy diễn rằng n nhỏ bảo đảm mọi tải.']
    path.write_text(old[:old.index(marker)]+'\n'.join(lines)+'\n',encoding='utf8')


if __name__=='__main__':main()
