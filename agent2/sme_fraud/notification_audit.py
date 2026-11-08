"""Append-only delivery history. Never log credentials or provider response bodies."""
import json
from .case_identity import digest


def history(db):
    result=[];previous=''
    for row in db.execute('SELECT * FROM notification_delivery_events ORDER BY sequence'):
        event=dict(sequence=row['sequence'],job_id=row['job_id'],kind=row['kind'],event_at=row['event_at'],
                   data=json.loads(row['data']),previous_hash=row['previous_hash'])
        if previous!=event['previous_hash'] or digest(event)!=row['event_hash']:
            raise ValueError('Nhật ký gửi thông báo không còn khớp; cần đối soát trước khi tiếp tục.')
        previous=row['event_hash'];result.append(dict(event,event_hash=previous))
    anchor=db.execute("SELECT value FROM settings WHERE key='notification_delivery_head'").fetchone()
    expected=dict(sequence=result[-1]['sequence'] if result else 0,event_hash=previous)
    if anchor and json.loads(anchor[0])!=expected or not anchor and result:
        raise ValueError('Nhật ký gửi thông báo bị thiếu hoặc đổi điểm kết thúc; cần đối soát.')
    return result


def append(db,job_id,kind,now,**data):
    previous=history(db)
    event=dict(sequence=previous[-1]['sequence']+1 if previous else 1,job_id=job_id,kind=kind,
               event_at=now.isoformat(),data=data,previous_hash=previous[-1]['event_hash'] if previous else '')
    db.execute('INSERT INTO notification_delivery_events VALUES(?,?,?,?,?,?,?)',
               (event['sequence'],job_id,kind,event['event_at'],json.dumps(data,ensure_ascii=False),event['previous_hash'],digest(event)))
    db.execute("INSERT INTO settings VALUES('notification_delivery_head',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (json.dumps(dict(sequence=event['sequence'],event_hash=digest(event))),))
