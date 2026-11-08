from enum import Enum
from typing import Generic, TypeVar

from pydantic import ConfigDict, model_validator

from .base import Contract, Identifier
from .evidence import Provenance, Unit

T = TypeVar('T')


def field_schema(schema):
    # Structural consumers enforce status/value too; cross-reference proof checks
    # still require the domain validators (see contracts README).
    schema['allOf'] = [
        {'if': {'properties': {'status': {'const': 'PRESENT'}}},
         'then': {'required': ['value'], 'properties': {'value': {'not': {'type': 'null'}}}},
         'else': {'properties': {'value': {'type': 'null'}}}},
        {'if': {'properties': {'confidence_basis': {'const': 'CALIBRATED'}}, 'required': ['confidence_basis']},
         'then': {'required': ['confidence'], 'properties': {
             'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
             'provenance': {'required': ['calibration_version'], 'properties': {'calibration_version': {'type': 'string', 'minLength': 1}}}}},
         'else': {'properties': {'confidence': {'type': 'null'}}}},
    ]
    for basis, key in [('DETERMINISTIC', 'deterministic_policy_version'), ('HUMAN_CONFIRMED', 'review_event_id')]:
        schema['allOf'].append({
            'if': {'properties': {'confidence_basis': {'const': basis}}, 'required': ['confidence_basis']},
            'then': {'properties': {'provenance': {'required': [key], 'properties': {key: {'type': 'string', 'minLength': 1}}}}},
        })


class FieldStatus(str, Enum):
    PRESENT = 'PRESENT'
    MISSING = 'MISSING'
    AMBIGUOUS = 'AMBIGUOUS'
    NOT_PROVIDED_BY_SOURCE = 'NOT_PROVIDED_BY_SOURCE'
    NOT_APPLICABLE = 'NOT_APPLICABLE'


class ConfidenceBasis(str, Enum):
    CALIBRATED = 'CALIBRATED'
    DETERMINISTIC = 'DETERMINISTIC'
    HUMAN_CONFIRMED = 'HUMAN_CONFIRMED'
    UNAVAILABLE = 'UNAVAILABLE'


class Candidate(Contract, Generic[T]):
    candidate_id: Identifier
    raw_value: str
    value: T
    provenance: Provenance


class FieldObject(Contract, Generic[T]):
    model_config = ConfigDict(json_schema_extra=field_schema)
    value: T | None = None
    status: FieldStatus
    confidence: Unit | None = None
    confidence_basis: ConfidenceBasis = ConfidenceBasis.UNAVAILABLE
    source: Identifier
    provenance: Provenance
    candidates: tuple[Candidate[T], ...] = ()

    @model_validator(mode='after')
    def semantics(self):
        if (self.status == FieldStatus.PRESENT) != (self.value is not None):
            raise ValueError('PRESENT requires value; every other status requires null')
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError('candidate IDs must be unique')
        basis = self.confidence_basis
        if basis == ConfidenceBasis.CALIBRATED:
            if self.confidence is None or not self.provenance.calibration_version:
                raise ValueError('CALIBRATED requires score and calibration version')
        elif self.confidence is not None:
            raise ValueError('only calibrated probabilities belong in confidence')
        if basis == ConfidenceBasis.DETERMINISTIC and not self.provenance.deterministic_policy_version:
            raise ValueError('DETERMINISTIC requires fidelity policy version')
        if basis == ConfidenceBasis.HUMAN_CONFIRMED and not self.provenance.review_event_id:
            raise ValueError('HUMAN_CONFIRMED requires review event ID')
        return self
