import json
import pandas as pd
from fastapi.testclient import TestClient
from agent1_service.api import create_app


def test_authenticated_csv_upload_and_foreign_schema_rejection(tmp_path,bank_registry):
    app=create_app(tmp_path,token='secret',firm_id='F000',bank_accounts_file=bank_registry())
    with TestClient(app) as client:
        headers={'Authorization':'Bearer secret'}
        raw='Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Tên đối tác,Nội dung\n15/03/2024,1000000,0,KH A,TT HD101\n'.encode('utf-8')
        statement=dict(account_id='A',currency='VND',period_start='2024-03-01',period_end='2024-03-31',
                       opening_balance='1000',closing_balance='1001000',total_credits='1000000',
                       total_debits='0',expected_accounts=['A'])
        result=client.post('/ingest/file',headers=headers,data={'kind':'bank_csv','bank':'vcb','statement':json.dumps(statement),'available_on':'2024-03-31'},files={'file':('bank.csv',raw,'text/csv')})
        assert result.status_code==200 and result.json()['accepted']==1
        assert client.get('/data',headers=headers).json()['bank_txns']==1
        assert client.get('/bank/coverage',headers=headers).json()['verified'] is True
        bad=client.post('/ingest/file',headers=headers,data={'kind':'bank_csv'},files={'file':('bad.csv',b'unrelated\n1\n','text/csv')})
        assert bad.status_code==422
