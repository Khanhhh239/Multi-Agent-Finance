from pathlib import Path
from .contracts import RuleSet,CapabilityProfile
from ..taxonomy.service import Taxonomy
from ..legal_registry.registry import load_registry

ROOT=Path(__file__).resolve().parents[2]/'rules/registry'


def load_catalog():
    return (RuleSet.model_validate_json((ROOT/'ruleset_v1.json').read_text(encoding='utf-8')),
            load_registry(),Taxonomy.model_validate_json((ROOT/'taxonomy_v1.json').read_text(encoding='utf-8')))


def load_capability(name):
    if name not in ('pdf_ocr_v1','invoice_xml_v1','bank_v1'):raise ValueError('unregistered profile')
    return CapabilityProfile.model_validate_json((ROOT/'capability_profiles'/ (name+'.json')).read_text(encoding='utf-8'))
