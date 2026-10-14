"""Generate restricted DRAFT tables; this never approves rules or legal mappings."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.rules.contracts import Binding
from src.rules.models import jdm
from src.persistence.repository import digest


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def main():
    registry=ROOT/'agent3_tax_compliance/rules/registry'
    output=ROOT/'agent3_tax_compliance/rules/models'
    rules=json.loads((registry/'ruleset_v1.json').read_text(encoding='utf-8'))
    rows=[]
    for family in rules['families']:
        for version in family['versions']:
            kind=version['family']
            if kind=='INVOICE_CONTENT':
                bindings=(Binding(condition_id='seller_tax_id_printed',operation='OBSERVATION_PRESENT',path='parties.seller.tax_id'),)
            elif kind=='VAT_RATE':
                bindings=(Binding(condition_id='taxable_treatment',operation='EQUALS',path='item.vat_treatment',expected='TAXABLE_RATE'),
                    Binding(condition_id='reduction_category',operation='EQUALS',path='item.vat_category',expected='REDUCTION_CANDIDATE'),
                    Binding(condition_id='rate_matches_draft_policy',operation='EQUALS',path='item.vat_rate',value_type='DECIMAL',expected='0.08'))
            else:
                bindings=(Binding(condition_id='non_cash_proof_verified',operation='PAYMENT_NON_CASH',path='payment.non_cash_evidence',value_type='BOOL'),)
            name=version['version']+'.jdm.json'
            write(output/name,jdm(bindings))
            row=dict(model_id=version['rule_id']+'.'+version['version'],version='draft-model-v1',
                rule_id=version['rule_id'],rule_version=version['version'],family=kind,unit_type=version['unit_type'],
                effective_from=version['effective_from'],effective_to=version['effective_to'],publication='DRAFT',
                legal_basis=version['legal_basis'],bindings=[b.model_dump(mode='json') for b in bindings],
                jdm_sha256=digest((output/name).read_bytes()),file=name)
            rows.append(row)
    write(output/'manifest.json',dict(package_id='agent3-technical-tax-models',version='technical-draft-20261015-v1',engine_version='0.53.0',models=rows))
    print('Built 7 DRAFT models; no legal release or auto-approval.')


if __name__=='__main__':main()
