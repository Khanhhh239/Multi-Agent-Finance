import importlib.util
from pathlib import Path
import sys
import pytest


def crawler():
    spec=importlib.util.spec_from_file_location('crawl_status_test',Path(__file__).resolve().parents[1]/'scripts/crawl.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_fetch_failure_is_nonzero_and_does_not_mark_source_complete(tmp_path,monkeypatch):
    module=crawler();module.RAW=tmp_path;module.MANIFEST=tmp_path/'MANIFEST.json'
    module.SOURCES={'test':dict(files=[('https://invalid.test/data','file')],license='test',role='test')}
    def fail(*_):raise OSError('network test')
    monkeypatch.setattr(module,'fetch',fail);monkeypatch.setattr(sys,'argv',['crawl.py','--only','test'])
    with pytest.raises(SystemExit):module.main()
    assert not module.MANIFEST.exists()


def test_multiple_sources_preserve_success_but_report_partial_failure(tmp_path,monkeypatch):
    module=crawler();module.RAW=tmp_path;module.MANIFEST=tmp_path/'MANIFEST.json'
    module.SOURCES={name:dict(files=[(name,name)],license='test',role='test') for name in ['ok','bad']}
    def fetch(url,dest):
        if url=='bad':raise OSError('network test')
        dest.write_text('data',encoding='utf-8');return dest
    monkeypatch.setattr(module,'fetch',fetch);monkeypatch.setattr(sys,'argv',['crawl.py','--only','ok,bad'])
    with pytest.raises(SystemExit):module.main()
    import json
    assert set(json.loads(module.MANIFEST.read_text()))=={'ok'}
