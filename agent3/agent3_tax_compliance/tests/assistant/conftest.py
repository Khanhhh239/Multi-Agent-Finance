"""Web tests act as a logged-in administrator unless a test says otherwise (test_admin.py checks the lock itself)."""
import pytest

from src.assistant import admin


@pytest.fixture(autouse=True)
def _admin_session(request, tmp_path, monkeypatch):
    monkeypatch.setattr(admin, 'STORE', tmp_path / 'admin.json')
    if 'real_admin' not in request.keywords:
        monkeypatch.setattr(admin, 'is_admin', lambda req: True)
    yield
    admin._sessions.clear()
    admin._fails.update(n=0, until=0.0)
