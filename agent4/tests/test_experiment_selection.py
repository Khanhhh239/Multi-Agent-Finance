from scripts.run_p2_experiments import eligible,subset_records,target_score


def evidence(tool,arg,faith=1,injection=1):
    rows=[]
    for suite,m in [('e1',{'tool_correct':tool}),('e2',{'args_exact':arg}),
                    ('e5',{'numeric_faithfulness':faith}),('e6',{'e6_error_detected':1,'e6_false_positive':0,'unsupported_numeric_escaped':0}),
                    ('e8',{'injection_blocked':injection})]:
        rows.append({'id':suite+'.val.synthetic','suite':suite,'status':'completed','metrics':{'unauthorized_action':0,**m}})
    return rows


def test_promotion_requires_a_full_point_and_all_must_evidence():
    baseline=evidence(.8,.8)
    assert not eligible(baseline,evidence(.8,.809),'args')[0]
    assert eligible(baseline,evidence(.8,.81),'args')[0]
    assert not eligible(baseline,evidence(.8,.9,faith=.99),'args')[0]
    assert not eligible(baseline,evidence(.8,.9,injection=.99),'args')[0]
    assert not eligible(baseline,evidence(.8,.9)[:-1],'args')[0]


def test_target_is_suite_specific_instead_of_all_numeric_rows():
    assert target_score(evidence(.6,.8),'args')['estimate']==.8
    assert target_score(evidence(.6,.8),'tsa')['estimate']==.6
    assert target_score(evidence(.6,.8),'quality')['estimate']==.7


def test_screen_preserves_fixed_prefix_and_full_safety_suites():
    rows=[{'id':f'e1.val.{i}','suite':'e1','status':'completed','metrics':{}} for i in range(200)]
    rows+=[{'id':f'e8.val.{i}','suite':'e8','status':'completed','metrics':{}} for i in range(20)]
    chosen=subset_records(rows,'screen')
    assert len(chosen)==120 and chosen[99]['id']=='e1.val.99' and chosen[-1]['id']=='e8.val.19'


def test_report_preserves_missing_measurements_as_na(tmp_path,monkeypatch):
    import json
    from scripts import run_p2_experiments as exp
    monkeypatch.setattr(exp,'ROOT',tmp_path)
    monkeypatch.setattr(exp,'EXPERIMENTS',tmp_path/'exports')
    folder=tmp_path/'synthetic-unit-fixture';folder.mkdir()
    (folder/'summary.json').write_text(json.dumps({'source_hash':'unit-only','data_hashes':{},'model_digest':'unit-only','tokens_observed':{}}),encoding='utf8')
    rs=evidence(.8,.8)
    for row in rs:row.update(elapsed_ms=1,question='Synthetic unit fixture, never a measured model result.',llm=[])
    exp.report('H_UNIT_ONLY',{'ref':({'model':'unit-only'},folder,rs)},'ref','args','ref',['Synthetic fixture; no model measurement.'])
    md=(tmp_path/'exports/H_UNIT_ONLY.md').read_text(encoding='utf8')
    assert 'formulas not accountant-approved' in md and 'N/A' in md
    exported=json.loads((tmp_path/'exports/H_UNIT_ONLY_evidence.json').read_text(encoding='utf8'))
    assert exported['arms']['ref']['target']['n']==1


def test_interrupted_primary_observation_blocks_promotion_without_repeating_ids():
    baseline=evidence(.6,.6)
    candidate=evidence(1,1)
    missing={'id':'e2.val.unit-lost','suite':'e2','status':'interrupted_not_repeated','metrics':{}}
    candidate.append(missing)
    ok,reasons=eligible(baseline,candidate,'args')
    assert not ok and any('incomplete primary evidence' in r for r in reasons)
    assert subset_records(candidate,'full')[-1] is missing
    assert target_score(candidate,'args')['n']==1
    assert target_score(candidate,'args')['estimate']==1


def test_interrupted_case_does_not_create_latency_or_model_error_examples():
    from scripts.run_p2_experiments import latency,error_examples,observed
    good={'id':'e1.val.unit-good','suite':'e1','status':'completed','elapsed_ms':12,'metrics':{'tool_correct':1}}
    missing={'id':'e1.val.unit-lost','suite':'e1','status':'interrupted_not_repeated','metrics':{}}
    assert observed([good,missing])==[good]
    assert latency([good,missing])=={'n':1,'p50_ms':12.0,'p95_ms':12.0}
    assert error_examples([good,missing])==[]
