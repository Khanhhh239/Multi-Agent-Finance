import json
from pathlib import Path

import pytest

from scripts.report_sealed_v4 import main
from agent2.world_v4_sealed import NOVEL


def fixture(monkeypatch, tmp_path, recalls, hard=.15):
    monkeypatch.chdir(tmp_path)
    Path('work/results').mkdir(parents=True)
    Path('results/v4').mkdir(parents=True)
    Path('docs/03_danh_gia_va_hieu_qua_kinh_te').mkdir(parents=True)
    frozen = {'chosen': 'L3', 'cold_start': 'Rules', 'dev_scores': {'L3': {'P1': .8}}}
    worlds = {}
    for seed, recall in zip((931, 932, 933), recalls):
        metrics = {'recall': recall, 'known_recall': .8, 'novel_recall': .4, 'case_recall': .9,
                   'new_decoy_alert_rate': .1, 'hard_neg_alert_rate': hard,
                   'by_family': {name: .4 for name in NOVEL}}
        worlds[f's4_s{seed}'] = {protocol: {'L3': metrics} for protocol in ('S1', 'S2')}
    Path('work/results/sealed_v4.json').write_text(json.dumps({'frozen': frozen, 'worlds': worlds}), encoding='utf-8')


def test_global_stop_and_g5_failure_are_recorded(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path, [.4, .4, .4])
    main()
    gates = json.loads(Path('results/v4/sealed_gates.json').read_text())
    assert gates['global_stop_triggered']
    assert not gates['g5_passed_macro_scenarios']
    assert not gates['sealed_reuse_permitted']


def test_macro_gate_keeps_individual_world_failure_visible(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path, [.49, .75, .8])
    main()
    gates = json.loads(Path('results/v4/sealed_gates.json').read_text())
    assert gates['g5_passed_macro_scenarios']
    assert not gates['g5_passed_all_world_scenarios']
    assert not gates['worlds']['s4_s931']['S1']['passed']
    assert not gates['global_stop_triggered']


def test_undefined_metrics_stop_before_reporting_or_training(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path, [float('nan'), .75, .8])
    with pytest.raises(ValueError, match='undefined sealed metrics'):
        main()
    assert not Path('results/v4/sealed_gates.json').exists()
