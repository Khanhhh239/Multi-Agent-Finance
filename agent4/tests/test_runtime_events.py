from eval.runtime_events import events


def test_runtime_capacity_audit_counts_only_new_bytes(tmp_path):
    path=tmp_path/'server.log';old=b'private prompt\nslot context shift\n'
    path.write_bytes(old+b'slot context shift\nslot release: truncated = 1\n')
    result=events(path,len(old))
    assert result['context_shift_events']==1 and result['truncated_request_events']==1
    assert 'private prompt' not in str(result)
    assert events(None)=={'measured':False}
