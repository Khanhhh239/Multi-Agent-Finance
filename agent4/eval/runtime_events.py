"""Count server-side capacity events without exposing prompt/log text."""
from pathlib import Path


def latest_log(root):
    paths=list(Path(root).glob('p2-ollama*.err.log'))
    return max(paths,key=lambda p:p.stat().st_mtime) if paths else None


def events(path,offset=0,end=None):
    if path is None or not Path(path).exists():return {'measured':False}
    with Path(path).open('rb') as f:f.seek(offset);data=f.read() if end is None else f.read(end-offset);end=f.tell()
    data=data.decode('utf8',errors='replace')
    return {'measured':True,'log':str(path),'start_byte':offset,'end_byte':end,
            'context_shift_events':data.count('slot context shift'),'truncated_request_events':data.count('truncated = 1'),
            'cuda_oom_messages':data.count('CUDA error: out of memory'),'scheduler_oom_events':data.count('runtime OOM detected;'),
            'model_load_events':data.count('loading model via llama-server'),'gpu_discovery_timeouts':data.count('GPU discovery watchdog timed out'),
            'note':'Server event counts, not distinct failed questions. RAM prompt cache disabled; active-slot KV prefix reuse remains enabled.'}
