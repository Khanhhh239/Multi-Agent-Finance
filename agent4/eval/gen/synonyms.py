import json
from pathlib import Path
from agent4.engine.metrics import REGISTRY

EXTRA=Path(__file__).with_name('extra_synonyms.json')


def synonyms(metric):
    extra=json.loads(EXTRA.read_text(encoding='utf8')) if EXTRA.exists() else {}
    md=REGISTRY[metric]
    return list(dict.fromkeys([md.label,*md.synonyms,*extra.get(metric,[])]))
