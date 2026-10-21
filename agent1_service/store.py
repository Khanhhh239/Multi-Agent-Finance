"""SQLite local mã hoá nội dung bản ghi; nhật ký chỉ giữ loại thao tác và số lượng."""
import json
from pathlib import Path
import sqlite3
import threading
from cryptography.fernet import Fernet


class Store:
    def __init__(self,path,key):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(path,check_same_thread=False)
        self.lock=threading.RLock()
        self.cipher=Fernet(key)
        self.connection.execute('CREATE TABLE IF NOT EXISTS records (firm TEXT, kind TEXT, id TEXT, payload BLOB, PRIMARY KEY(firm,kind,id))')
        self.connection.execute('CREATE TABLE IF NOT EXISTS audit (at TEXT DEFAULT CURRENT_TIMESTAMP, firm TEXT, action TEXT, count INTEGER)')
        self.connection.commit()

    def put(self,firm,kind,records):
        with self.lock,self.connection:
            for row in records:
                identifier=str(row['id'])
                payload=self.cipher.encrypt(json.dumps(row,ensure_ascii=False,allow_nan=False).encode())
                self.connection.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)',(firm,kind,identifier,payload))
            self.connection.execute('INSERT INTO audit(firm,action,count) VALUES (?,?,?)',(firm,'put:'+kind,len(records)))

    def get(self,firm,kind):
        with self.lock:
            rows=self.connection.execute('SELECT payload FROM records WHERE firm=? AND kind=? ORDER BY id',(firm,kind)).fetchall()
        return [json.loads(self.cipher.decrypt(row[0])) for row in rows]

    def delete_firm(self,firm):
        with self.lock,self.connection:
            self.connection.execute('DELETE FROM records WHERE firm=?',(firm,))
            self.connection.execute('INSERT INTO audit(firm,action,count) VALUES (?,?,?)',(firm,'delete',0))
        # Sau xoá, VACUUM loại trang chứa bản mã cũ khỏi DB chính.
        with self.lock:
            self.connection.execute('VACUUM')
