import numpy as np
import pandas as pd
import pytest

from agent2.base_v5 import MatrixSequence, fit_source, observed_labels, verify_storage_revision
from agent2.runtime_v5 import write_json


def test_stream_matrix_matches_dense_rows_slices_and_columns(tmp_path):
    x=np.random.default_rng(2).normal(size=(113,17)).astype(np.float32)
    path=tmp_path/'matrix.npy'; np.save(path,x)
    sequence=MatrixSequence(path,[3,0,12])
    np.testing.assert_array_equal(sequence[7],x[7,[3,0,12]])
    np.testing.assert_array_equal(sequence[2:19],x[2:19][:,[3,0,12]])
    np.testing.assert_array_equal(sequence[[1,6,2]],x[[1,6,2]][:,[3,0,12]])
    assert len(sequence)==113


def test_hidden_source_branch_is_unknown_in_both_train_and_validation():
    metadata=pd.DataFrame(dict(is_fraud=[0,1,1,1,1],fraud_type=['','a','a','b','c'],
                               branch=['','x','x','y','z']))
    y,weights=observed_labels(metadata,hidden='x',balanced=True,weight=.2)
    assert y.tolist()==[0,0,0,1,1]
    np.testing.assert_allclose(weights,[.2,.2,.2,1,1])
    # Hidden true family strings cannot affect observed positive balancing.
    metadata.loc[metadata.branch=='x','fraud_type']='hidden_elsewhere'
    y2,w2=observed_labels(metadata,hidden='x',balanced=True,weight=.2)
    np.testing.assert_array_equal(y,y2)
    np.testing.assert_array_equal(weights,w2)


def test_streamed_PU_fit_uses_nineteen_sources_and_hidden_branch(tmp_path):
    rng=np.random.default_rng(34)
    for seed in range(1001,1021):
        directory=tmp_path/f's{seed}'
        directory.mkdir()
        write_json(directory/'manifest.json',dict(columns=['x','z'],L3_columns=['x']))
        for split,n in [('train',48),('validation',24),('test',12)]:
            x=rng.normal(size=(n,2)).astype(np.float32)
            np.save(directory/f'{split}.npy',x)
            y=np.arange(n)%4==0
            branch=np.where(y,np.where(np.arange(n)%8==0,'a','b'),'')
            pd.DataFrame(dict(is_fraud=y.astype(int),branch=branch,
                             fraud_type=np.where(y,branch,''))).to_parquet(directory/f'{split}.parquet',index=False)
    scores,details=fit_source(1001,tmp_path,'a',.2,max_rounds=12,early_stop=3)
    assert len(scores)==12 and np.isfinite(scores).all()
    assert np.all((scores>=0)&(scores<=1))
    assert details['source_worlds']==19 and details['source_train_rows']==19*48
    assert details['source_validation_rows']==19*24
    assert details['source_observed_train_positives']==19*6


def test_storage_migration_blocks_models_if_full_world_bytes_change(tmp_path):
    write_json(tmp_path/'io_revision1'/'migration_proof.json',{'partial_1013_csv_sha256':{'features.csv':'abc','labels.csv':'def'}})
    write_json(tmp_path/'world_1013.json',{'file_hashes':{'features.csv':'abc','labels.csv':'def'}})
    verify_storage_revision(tmp_path)
    write_json(tmp_path/'world_1013.json',{'file_hashes':{'features.csv':'changed','labels.csv':'def'}})
    with pytest.raises(ValueError,match='Full-world storage equivalence failed'):
        verify_storage_revision(tmp_path)
