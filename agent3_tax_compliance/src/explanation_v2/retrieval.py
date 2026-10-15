"""NFC BM25, strictly restricted to planner-selected document/hash/locator."""
import math
import re
import unicodedata
from collections import Counter
from datetime import date
from .contracts import Corpus


def tokens(text):
    return re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold())


def retrieve(corpus: Corpus, registry, citations, query, on: date, top_k=3):
    if corpus.registry_version != registry.version:
        raise ValueError('Corpus registry version differs from pinned evaluation')
    docs = {d.document_id: d for d in registry.documents}
    allowed = {(c.document_id, c.locator, c.sha256) for c in citations
               if c.locator_reviewed}
    candidates = []
    for chunk in corpus.chunks:
        if (chunk.document_id, chunk.locator, chunk.document_sha256) not in allowed:
            continue
        doc = docs.get(chunk.document_id)
        if not doc or doc.source_status != 'PDF_REVIEWED' or doc.sha256 != chunk.document_sha256:
            continue
        if chunk.locator not in doc.verified_locators:
            continue
        if (chunk.effective_from, chunk.effective_to) != (doc.effective_from, doc.effective_to):
            continue
        if not chunk.effective_from <= on or chunk.effective_to and on >= chunk.effective_to:
            continue
        candidates.append(chunk)
    if not candidates:
        return ()
    bags = [Counter(tokens(c.text)) for c in candidates]
    avg = sum(sum(b.values()) for b in bags) / len(bags) or 1
    terms = set(tokens(query))
    df = {t: sum(t in b for b in bags) for t in terms}
    def score(bag):
        size = sum(bag.values())
        return sum(math.log(1 + (len(bags)-df[t]+.5)/(df[t]+.5)) *
                   (bag[t]*2.2)/(bag[t]+1.2*(.25+.75*size/avg))
                   for t in terms if bag[t])
    ranked = sorted(zip(candidates, bags), key=lambda pair: (-score(pair[1]), pair[0].chunk_id))
    return tuple(c for c, _ in ranked[:top_k])
