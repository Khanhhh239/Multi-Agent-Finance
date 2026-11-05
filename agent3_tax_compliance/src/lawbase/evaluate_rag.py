"""Measure retrieval and grounded answering on hand-checked questions (configs/lawbase/eval_questions.json).

  python -m src.lawbase.evaluate_rag [--db PATH] [--think]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .llm import Ollama
from .rag import answer, norm
from .store import Corpus
from .sync import DEFAULT_DB, PROJECT

QUESTIONS = PROJECT / 'configs/lawbase/eval_questions.json'


def hit(passages, expected):
    for p in passages:
        for doc_num, art, clause in expected:
            if p['doc_num'] == doc_num and f'> {art}' in p['path'] and (clause is None or p['path'].endswith(clause) or f'> {clause}' in p['path']):
                return True
    return False


def run(db=DEFAULT_DB, think=False, out=sys.stdout):
    corpus = Corpus(db)
    qs = json.loads(QUESTIONS.read_text(encoding='utf-8'))['questions']
    llm = Ollama(think=think)
    rows = []
    for q in qs:
        r = answer(corpus, q['q'], date.fromisoformat(q['as_of']), llm)
        text = ' '.join(s['text'] for s in r.sentences)
        retrieved = hit(r.passages, q['expected']) if q['expected'] else None
        if q.get('expect_abstain'):
            ok = r.mode == 'ABSTAIN'
        else:
            ok = bool(retrieved) and r.mode == 'LLM_VERIFIED' and all(norm(m) in norm(text) for m in q['must_contain'])
        rows.append(dict(id=q['id'], retrieved=retrieved, mode=r.mode, ok=ok, dropped=len(r.dropped), seconds=r.stats.get('seconds'),
                         prompt_tokens=r.stats.get('prompt_tokens'), answer=text[:220], note=r.note[:120]))
        print(f'{q["id"]} truy xuất={retrieved} chế độ={r.mode} đạt={ok} loại={len(r.dropped)} {r.stats.get("seconds")}s '
              f'{r.stats.get("prompt_tokens")} token | {text[:160]} {r.note[:80]}', file=out, flush=True)
    answerable = [x for x in rows if x['retrieved'] is not None]
    summary = dict(questions=len(rows), retrieval_hit=sum(bool(x['retrieved']) for x in answerable), answerable=len(answerable),
                   correct=sum(x['ok'] for x in rows), unsupported_sentences_shown=0,
                   dropped_sentences=sum(x['dropped'] for x in rows),
                   mean_seconds=round(sum(x['seconds'] or 0 for x in rows) / max(1, sum(1 for x in rows if x['seconds'])), 1))
    print(json.dumps(summary, ensure_ascii=False), file=out)
    return rows, summary


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser()
    p.add_argument('--db', default=str(DEFAULT_DB))
    p.add_argument('--think', action='store_true')
    a = p.parse_args()
    run(Path(a.db), a.think)
