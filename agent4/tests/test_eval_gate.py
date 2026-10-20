import json
import pytest
from eval.gate import require_split_access,freeze,start_final,started_ids,claim_final,require_not_consumed,acquire_final_lease


def test_test_rows_cannot_be_opened_by_regular_runner():
    with pytest.raises(ValueError,match='Sealed'):require_split_access('test')
    require_split_access('val');require_split_access('test',True)


def test_only_one_final_start_and_exact_frozen_resume(tmp_path):
    config={'model':'fake','k':8};hashes={'e1':'abc'}
    lock=freeze(tmp_path/'lock.json',config,'digest',hashes,'source')
    folder=tmp_path/'final';start_final(folder,lock,config,'digest',hashes,'source')
    with pytest.raises(ValueError,match='already started'):start_final(folder,lock,config,'digest',hashes,'source')
    start_final(folder,lock,config,'digest',hashes,'source',resume=True)
    for changed in ({'model':'fake','k':5},{'model':'other','k':8}):
        with pytest.raises(ValueError,match='mismatch'):start_final(folder,lock,changed,'digest',hashes,'source',resume=True)
    with pytest.raises(ValueError,match='mismatch'):start_final(folder,lock,config,'other',hashes,'source',resume=True)


def test_started_but_lost_result_is_recognized_without_repeating_case(tmp_path):
    journal=tmp_path/'started.jsonl';journal.write_text(json.dumps({'id':'case1'})+'\n',encoding='utf8')
    assert started_ids(journal)=={'case1'} and started_ids(tmp_path/'missing')==set()


def test_turn_used_in_tuning_excludes_entire_conversation():
    from eval.run import excluded
    from eval.gen.split import question_hash
    case={'question':'Whole new conversation','turns':[{'user':'Known tuning turn'}]}
    assert excluded(case,{question_hash('known tuning turn!')})


def test_final_cannot_repeat_under_a_different_output_folder(tmp_path):
    marker=tmp_path/'seal'/'claimed.json';out=tmp_path/'first'
    claim_final(marker,out)
    claim_final(marker,out,resume=True)
    with pytest.raises(ValueError,match='already claimed'):claim_final(marker,out)
    with pytest.raises(ValueError,match='original output'):claim_final(marker,tmp_path/'second',resume=True)


def test_published_completion_receipt_prevents_a_fresh_checkout_rerun(tmp_path):
    receipt=tmp_path/'consumed.json';require_not_consumed(receipt)
    receipt.write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='already completed'):require_not_consumed(receipt)


def test_two_processes_cannot_resume_one_final_run_at_once(tmp_path):
    path=tmp_path/'active.lock'
    first=acquire_final_lease(path)
    try:
        with pytest.raises(ValueError,match='concurrently'):acquire_final_lease(path)
    finally:first.close()
    second=acquire_final_lease(path);second.close()
