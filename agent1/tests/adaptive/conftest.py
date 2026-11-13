"""Shared browser and Portal setup for Workspace integration tests."""
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest


@pytest.fixture
def portal_module(tmp_path, monkeypatch):
    """Load a fresh Portal with its sibling imports and storage kept in the test."""
    path = Path(__file__).resolve().parents[3] / 'portal' / 'server.py'
    config = json.loads((path.parent / 'config.example.json').read_text(encoding='utf-8'))
    config['workspace'] = str(tmp_path / 'portal-workspace')
    config_path = tmp_path / 'portal-config.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setenv('MAF_PORTAL_CONFIG', str(config_path))
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('agent1_test_portal', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def browser_runtime():
    playwright = pytest.importorskip('playwright.sync_api')
    chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    if not chrome.exists():
        pytest.skip('Chrome is not installed')
    return playwright, chrome


@pytest.fixture
def client_proxy():
    """Route browser requests through the test's authenticated, isolated client."""
    def for_client(client):
        def proxy(route):
            request = route.request
            url = urlsplit(request.url)
            response = client.request(
                request.method,
                url.path + ('?' + url.query if url.query else ''),
                content=request.post_data_buffer,
                headers={'Content-Type': request.headers.get('content-type', 'application/json')},
            )
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={key: value for key, value in response.headers.items()
                         if key not in ('content-length', 'content-encoding')},
            )
        return proxy
    return for_client
