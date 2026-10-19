import hashlib
from agent4.agent.retriever import normalize


def question_hash(question):
    return hashlib.sha256(normalize(question).encode()).hexdigest()


def assert_disjoint(records):
    owners={};questions={}
    for split,rows in records.items():
        for row in rows:
            tid=row['template_id'];digest=question_hash(row.get('question',' '.join(t['user'] for t in row.get('turns',[]))))
            if tid in owners and owners[tid]!=split: raise ValueError('template leakage')
            if digest in questions: raise ValueError('normalized question duplicate')
            owners[tid]=split;questions[digest]=split

