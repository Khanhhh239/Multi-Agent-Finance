import ast
import copy
import inspect

from sme_fraud.generate import Generator, save_dataset
from agent2.world_v5_io import save_dataset_streamed


def test_streamed_writer_has_only_registered_storage_changes():
    old=inspect.getsource(save_dataset)
    expected=old.replace('def save_dataset(', 'def save_dataset_streamed(',1).replace(
        'from .features import build_features, FEATURE_DESCRIPTIONS',
        'from sme_fraud.features import build_features, FEATURE_DESCRIPTIONS').replace(
        'hashlib.sha256(path.read_bytes()).hexdigest()','sha256(path)')
    assert ast.dump(ast.parse(expected))==ast.dump(ast.parse(inspect.getsource(save_dataset_streamed)))


def test_streamed_writer_produces_identical_csv_manifest_and_dictionary(tmp_path):
    tables=Generator(10_000,.005,511,2).finalize()
    original=tmp_path/'original'; streamed=tmp_path/'streamed'
    a=save_dataset(original,copy.deepcopy(tables),10000,.005,511,2)
    b=save_dataset_streamed(streamed,copy.deepcopy(tables),10000,.005,511,2)
    assert a==b
    assert {p.name for p in original.iterdir()}=={p.name for p in streamed.iterdir()}
    for p in original.iterdir():
        assert p.read_bytes()==(streamed/p.name).read_bytes(),p.name
