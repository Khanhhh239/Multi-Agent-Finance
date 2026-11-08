"""Strict grounded rendering: no arbitrary prose accepted in the first release."""
import unicodedata
from .contracts import LLMOutput, Claim


def fallback(context):
    return tuple(Claim(fact_id=f.fact_id, text=f.variants[0], refs=f.refs) for f in context.facts)


def validate(raw, context):
    result = LLMOutput.model_validate_json(raw)
    facts = {f.fact_id: f for f in context.facts}
    if len(result.claims) != len(facts) or {c.fact_id for c in result.claims} != set(facts):
        raise ValueError('Omitted, duplicated, or invented claim')
    normalized = []
    for claim in result.claims:
        fact = facts[claim.fact_id]
        text = unicodedata.normalize('NFC', claim.text)
        if text not in tuple(unicodedata.normalize('NFC', t) for t in fact.variants):
            raise ValueError('Unsupported claim text')
        if claim.refs != fact.refs:
            raise ValueError('Claim references changed')
        normalized.append(Claim(fact_id=claim.fact_id, text=text, refs=fact.refs))
    return tuple(normalized)
