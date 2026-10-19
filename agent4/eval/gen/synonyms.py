import json
from pathlib import Path
from agent4.engine.metrics import REGISTRY
from agent4.agent.retriever import normalize

EXTRA=Path(__file__).with_name('extra_synonyms.json')


def synonyms(metric):
    extra=json.loads(EXTRA.read_text(encoding='utf8')) if EXTRA.exists() else {}
    md=REGISTRY[metric]
    out=[];seen=set()
    for phrase in [md.label,*md.synonyms,*extra.get(metric,[])]:
        key=normalize(phrase)
        if key not in seen:out.append(phrase);seen.add(key)
    return out
