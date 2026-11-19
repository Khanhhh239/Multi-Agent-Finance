"""Static checks for the Vercel and Render cloud image contracts."""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

import pytest
from cloud.build_portal_static import build


def test_render_blueprint_uses_single_free_web_service_and_healthz():
    render = (_ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "type: web" in render
    assert "plan: free" in render
    assert "dockerfilePath: ./cloud/Dockerfile" in render
    assert "healthCheckPath: /healthz" in render
    assert "AGENT4_DEMO_MODE" in render
    assert "AGENT4_MAX_CONCURRENT_QUERIES" in render
    assert "DATABASE_URL" in render


def test_cloud_image_excludes_datagen_and_local_agents():
    dockerfile = (_ROOT / "cloud/Dockerfile").read_text(encoding="utf-8")
    requirements = (_ROOT / "agent4/requirements-cloud.txt").read_text(encoding="utf-8")
    entrypoint = (_ROOT / "cloud/entrypoint.sh").read_text(encoding="utf-8")
    assert "COPY agent4/agent4 /app/agent4" in dockerfile
    assert "COPY agent1" not in dockerfile
    assert "COPY agent2" not in dockerfile
    assert "COPY agent3" not in dockerfile
    assert "pandas" not in requirements.lower()
    assert "--host 0.0.0.0" in entrypoint
    assert '"${PORT:-10000}"' in entrypoint
    assert "create_cloud_app" in entrypoint


def test_vercel_build_contains_only_public_runtime_config(monkeypatch, tmp_path):
    monkeypatch.setenv("MAF_API_BASE_URL", "https://gateway.example.test")
    monkeypatch.setenv("MAF_ENABLED_AGENTS", "agent4")
    output = build(tmp_path / "portal")
    runtime = (output / "runtime-config.js").read_text(encoding="utf-8")
    assert '"apiBaseUrl":"https://gateway.example.test"' in runtime
    assert '"enabledAgents":["agent4"]' in runtime
    assert "API_KEY" not in runtime
    assert (output / "index.html").is_file()
    assert (output / "agent4" / "index.html").is_file()
    assert (output / "agent4" / "chat.js").is_file()
    assert (output / "design" / "platform-theme.css").is_file()
    assert not (output / "design" / "sync.py").exists()
    assert not (output / "agent4" / "README.md").exists()


def test_vercel_config_is_static_and_has_no_serverless_backend():
    config = json.loads((_ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["outputDirectory"] == "build/portal-static"
    assert config["buildCommand"] == "python3 cloud/build_portal_static.py"
    assert "functions" not in config
    assert any(header["key"] == "Content-Security-Policy" for header in config["headers"][0]["headers"])
    assert any(rewrite["source"] == "/agent4" for rewrite in config["rewrites"])


def test_vercel_build_rejects_non_https_api_or_unknown_capability(monkeypatch, tmp_path):
    monkeypatch.setenv("MAF_API_BASE_URL", "http://gateway.example.test")
    with pytest.raises(SystemExit, match="HTTPS"):
        build(tmp_path / "bad-http")
    monkeypatch.setenv("MAF_API_BASE_URL", "https://gateway.example.test")
    monkeypatch.setenv("MAF_ENABLED_AGENTS", "agent5")
    with pytest.raises(SystemExit, match="agent1"):
        build(tmp_path / "bad-agent")
