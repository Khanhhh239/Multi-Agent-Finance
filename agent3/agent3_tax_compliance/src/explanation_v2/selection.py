"""Compact model choices; authoritative text and references stay on the server."""
import json
from pydantic import Field, StrictInt
from ..domain.base import Contract
from .contracts import Claim, LLMOutput


class Selection(Contract):
    fact_id: str
    variant_index: StrictInt = Field(ge=0)


class SelectionOutput(Contract):
    selections: tuple[Selection, ...] = Field(min_length=1, max_length=100)


def selectable_facts(context):
    # Legal quotations are immutable, often long, and have no editorial choice.
    # Keep them in the final artifact without asking a model to reproduce them.
    return tuple(f for f in context.facts if not f.fact_id.startswith('quote:'))


def request_data(context):
    facts = selectable_facts(context)
    if not facts:
        raise ValueError('No selectable facts')
    schema = SelectionOutput.model_json_schema()
    schema['$defs']['Selection']['properties']['fact_id']['enum'] = [f.fact_id for f in facts]
    schema['properties']['selections'].update(minItems=len(facts), maxItems=len(facts))
    content = json.dumps({'facts': [{'fact_id': f.fact_id, 'variants': f.variants} for f in facts]},
                         ensure_ascii=False, separators=(',', ':'))
    return content, schema


def materialize(raw, context):
    result = SelectionOutput.model_validate_json(raw)
    facts = {f.fact_id: f for f in selectable_facts(context)}
    ids = [s.fact_id for s in result.selections]
    if len(ids) != len(facts) or set(ids) != set(facts):
        raise ValueError('Omitted, duplicated, or invented selection')
    claims = []
    for selection in result.selections:
        fact = facts[selection.fact_id]
        if selection.variant_index >= len(fact.variants):
            raise ValueError('Unsupported variant index')
        claims.append(Claim(fact_id=fact.fact_id, text=fact.variants[selection.variant_index], refs=fact.refs))
    claims.extend(Claim(fact_id=f.fact_id, text=f.variants[0], refs=f.refs)
                  for f in context.facts if f.fact_id.startswith('quote:'))
    return LLMOutput(claims=tuple(claims)).model_dump_json()
