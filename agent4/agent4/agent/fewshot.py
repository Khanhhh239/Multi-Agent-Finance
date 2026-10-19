"""TRAIN-only oracle-labeled examples, ranked locally by BM25."""
import json
from pathlib import Path
from rank_bm25 import BM25Okapi
from .retriever import normalize

PATH=Path(__file__).parent/'data/fewshot_train.jsonl'

class FewShotBank:
    def __init__(self,path=PATH):
        self.examples=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
        if any(e.get('split')!='train' for e in self.examples): raise ValueError('Few-shot chỉ nhận TRAIN.')
        self.index=BM25Okapi([normalize(e['question']).split() for e in self.examples])

    def select_examples(self,question,k=3):
        scores=self.index.get_scores(normalize(question).split())
        ranked=sorted(enumerate(self.examples),key=lambda pair:(-scores[pair[0]],pair[0]))
        chosen=[e for _,e in ranked if normalize(e['question'])!=normalize(question)][:k]
        return [{'question':e['question'],'answer':e['answer']} for e in chosen]

def select_examples(question,k=3):
    return FewShotBank().select_examples(question,k)
