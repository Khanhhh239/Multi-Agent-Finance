"""Synthetic producer mapping explicit native master facts to opt-in snapshots."""
from copy import deepcopy
from .native_rule_demo import scenario


MODES=('signal','control','phone_only','address_only','declared')


def prepare(mode='signal',company='C001'):
    if mode not in MODES:raise ValueError('Unknown synthetic scenario')
    native,_=scenario('B5',mode!='control',company)
    tables=native['tables'];vendors=tables['vendors'];first,peer=vendors
    if mode=='phone_only':peer['bank_account']='SIM_OTHER_BANK'
    if mode=='address_only':
        peer.update(bank_account='SIM_OTHER_BANK',phone='0902111111',address=first['address'])
    if mode=='declared':
        for v in vendors:v['related_party_disclosed_at']='2023-01-01T00:00:00+07:00'
    def common(record,identity,time):
        return dict(tenant_id='native-demo',company_id=company,record_id=identity,revision=1,
            observed_at=time,effective_at=time,
            source=dict(system='synthetic-native-export',record_id=identity,is_simulated=True))
    data=dict(contract_version='1.2.0',tenant_id='native-demo',companies=[],vendors=[],transactions=[],
        employees=[],invoices=[],payment_allocations=[],approvals=[],supporting_documents=[],vendor_bank_history=[])
    # This is a synthetic source producer. The server never fills source dates
    # or missing identity fields; every canonical value is explicit in this file.
    for row in tables['companies']:
        data['companies'].append(dict(common(row,company,row['recorded_at']),name=row['name']))
    for row in tables['vendors']:
        data['vendors'].append(dict(common(row,row['vendor_id'],row['recorded_at']),name=row['name'],
            **{k:row[k] for k in ('bank_account','bank_code','address','phone','related_party_disclosed_at')}))
    for row in tables['employees']:
        data['employees'].append(dict(common(row,row['employee_id'],row['recorded_at']),name=row['full_name'],role=row['role']))
    for row in tables['transactions']:
        data['transactions'].append(dict(common(row,row['transaction_id'],row['observed_at']),effective_at=row['posted_at'],
            amount_vnd=row['amount_vnd'],currency=row['currency'],kind='payment',description=row['business_purpose'],
            vendor_ref=dict(record_id=row['vendor_id'],revision=1),created_by_ref=dict(record_id=row['creator_id'],revision=1),
            bank_account=row['recipient_account'],bank_code=row['recipient_bank_code'],payment_channel=row['payment_channel']))
    return data,deepcopy(tables),native['as_of']
