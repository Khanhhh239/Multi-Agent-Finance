import io
import json
import numpy as np
import pandas as pd
import pytest
from agent1_service.ingest.bank_statement import BANK_COLUMNS,normalize_statement,read_statement
from agent1_service.ingest.privacy import anonymize
from agent1_service.ingest.einvoice_xml import read_invoice_xml
from agent1.synth.einvoice import invoice_to_xml
from agent1.synth.names import make_mst


@pytest.mark.parametrize('bank',list(BANK_COLUMNS))
@pytest.mark.parametrize('extension',['csv','xlsx'])
def test_bank_format_roundtrip(bank,extension,tmp_path):
    canonical=pd.DataFrame({'value_date':['15/03/2024','16/03/2024'],'amount':[1234000.,9876000.],
                            'counterparty':['KH A','KH B'],'memo':['HD 00000101','TT HD 00000102']})
    native=canonical.rename(columns={v:k for k,v in BANK_COLUMNS[bank].items()})
    path=tmp_path/f'bank.{extension}'
    if extension=='csv':native.to_csv(path,index=False)
    else:native.to_excel(path,index=False)
    normalized=read_statement(path,'F000',bank)
    assert normalized.amount.tolist()==canonical.amount.tolist()
    assert normalized.value_date.iloc[0]==pd.Timestamp('2024-03-15')
    assert normalized.memo.tolist()==canonical.memo.tolist()


def test_identical_bank_rows_remain_distinct_transactions():
    raw=pd.DataFrame({'value_date':['15/03/2024']*2,'amount':[100.,100.],'memo':['same']*2})
    result=normalize_statement(raw,'F000',mapping={})
    assert result.txn_id.nunique()==2


def test_hmac_requires_key_and_is_scoped_by_tenant_key():
    one=anonymize('0100109106',b'a'*32)
    assert one==anonymize('0100109106',b'a'*32)
    assert one!=anonymize('0100109106',b'b'*32)
    with pytest.raises(ValueError):anonymize('name',b'short')


def test_xml_namespace_roundtrip_and_entity_rejection():
    rng=np.random.default_rng(7)
    seller=pd.Series({'name':'Seller','mst':make_mst(rng)})
    buyer=pd.Series({'name':'Buyer','mst':make_mst(rng)})
    inv=pd.Series(dict(invoice_id='i',symbol='1C24TAA',invoice_no='00000001',issue_date='2024-01-01',due_date='2024-01-31',
                        amount_net=1000000.,amount_gross=1100000.,vat_rate=.1,term_days=30,currency='VND'))
    content=invoice_to_xml(inv,seller,buyer).replace(b'<HDon>',b'<HDon xmlns="urn:test">')
    row=read_invoice_xml(content,'F000')
    assert row['amount_gross']==1100000 and row['invoice_id']=='i'
    with pytest.raises(ValueError):read_invoice_xml(b'<!DOCTYPE x [<!ENTITY test "x">]><HDon/>','F000')
