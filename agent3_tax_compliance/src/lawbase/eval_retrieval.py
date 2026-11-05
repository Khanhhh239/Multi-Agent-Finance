"""Retrieval only, no model: is an expected provision among the passages packed for the model (hit), and at which rank.
Compares keyword search with hybrid (keyword + bge-m3) on the development set and the held-out set.

  python -m src.lawbase.eval_retrieval
"""
import json
import sys
from datetime import date

from .evaluate_rag import hit
from .rag import pack
from .store import Corpus
from .sync import DEFAULT_DB, PROJECT

SETS = {'phát triển': PROJECT / 'configs/lawbase/eval_questions.json', 'giữ lại': PROJECT / 'configs/lawbase/eval_questions_holdout.json'}


def first_rank(passages, expected):
    for n, p in enumerate(passages, 1):
        if hit([p], expected):
            return n
    return None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c = Corpus(DEFAULT_DB)
    for name, path in SETS.items():
        qs = [q for q in json.loads(path.read_text(encoding='utf-8'))['questions'] if q['expected']]
        for hybrid in (False, True):
            c.hybrid = hybrid
            ranks = [first_rank([p.__dict__ for p in pack(c, q['q'], date.fromisoformat(q['as_of']))], q['expected']) for q in qs]
            hits = sum(r is not None for r in ranks)
            top1 = sum(r == 1 for r in ranks)
            mrr = sum(1 / r for r in ranks if r) / len(ranks)
            miss = [q['id'] for q, r in zip(qs, ranks) if r is None]
            print(f'{name:10} {"lai (từ khóa + ngữ nghĩa)" if hybrid else "từ khóa":28} trúng {hits}/{len(qs)}  đứng đầu {top1}/{len(qs)}  MRR {mrr:.3f}  trượt {miss}')


if __name__ == '__main__':
    main()
