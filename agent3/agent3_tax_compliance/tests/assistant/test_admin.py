"""The settings lock: changes to configuration need the administrator password; daily work does not."""
import pytest
from fastapi.testclient import TestClient

from src.assistant import admin, web

pytestmark = pytest.mark.real_admin


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'WORKSPACES', tmp_path / 'ws')
    monkeypatch.setattr(admin, 'STORE', tmp_path / 'admin.json')
    return TestClient(web.app)


def test_settings_are_locked_until_login(client):
    assert client.get('/api/admin/status').json() == dict(configured=False, logged_in=False, ttl_minutes=30)
    r = client.post('/api/demo')
    assert r.status_code == 401 and r.json()['admin_required']
    assert client.post('/api/admin/setup', json=dict(password='ngan')).status_code == 422
    assert client.post('/api/admin/setup', json=dict(password='mat-khau-dai')).status_code == 200
    assert client.post('/api/admin/setup', json=dict(password='mat-khau-khac')).status_code == 409
    wid = client.post('/api/demo').json()['id']                       # the setup call logged the administrator in
    client.post('/api/admin/logout')
    assert client.put(f'/api/workspaces/{wid}/pack', json={}).status_code == 401
    assert client.post(f'/api/workspaces/{wid}/run').status_code == 200   # daily work stays open
    assert client.post('/api/admin/login', json=dict(password='sai-mat-khau')).status_code == 401
    assert client.post('/api/admin/login', json=dict(password='mat-khau-dai')).status_code == 200
    assert client.get('/api/admin/status').json()['logged_in']
    assert 'mat-khau-dai' not in (admin.STORE.read_text(encoding='utf-8'))


def test_repeated_wrong_passwords_lock_logins(client):
    client.post('/api/admin/setup', json=dict(password='mat-khau-dai'))
    codes = [client.post('/api/admin/login', json=dict(password='sai')).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_catalog_edit_needs_login_and_validates(client):
    client.post('/api/admin/setup', json=dict(password='mat-khau-dai'))
    data = client.get('/api/admin/catalog/holidays').json()['data']
    bad = dict(data, years={'2027': [dict(date='2026-05-05', name='x')]})
    assert client.put('/api/admin/catalog/holidays?by=kt', json=bad).status_code == 422
    client.post('/api/admin/logout')
    assert client.put('/api/admin/catalog/holidays?by=kt', json=data).status_code == 401
