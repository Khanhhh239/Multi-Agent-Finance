import pandas as pd
from fastapi.testclient import TestClient
from agent1_service.api import create_app


def test_authenticated_csv_upload_and_foreign_schema_rejection(tmp_path):
    app=create_app(tmp_path,token='secret',firm_id='F000')
    with TestClient(app) as client:
        headers={'Authorization':'Bearer secret'}
        raw='Ngày giao dịch,Số tiền ghi có,Tên đối tác,Nội dung\n15/03/2024,1000000,KH A,TT HD101\n'.encode('utf-8')
        result=client.post('/ingest/file',headers=headers,data={'kind':'bank_csv','bank':'vcb'},files={'file':('bank.csv',raw,'text/csv')})
        assert result.status_code==200 and result.json()['accepted']==1
        assert client.get('/data',headers=headers).json()['bank_txns']==1
        bad=client.post('/ingest/file',headers=headers,data={'kind':'bank_csv'},files={'file':('bad.csv',b'unrelated\n1\n','text/csv')})
        assert bad.status_code==422
