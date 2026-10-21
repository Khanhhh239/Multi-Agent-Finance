import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sprint1'))
from publish_sprint1 import validate_paths


@pytest.mark.parametrize('path',['data/raw/bank.csv','data/processed/snap.parquet','.state/api-token.txt',
    'outputs/model.dat','secret.key','.env','../outside.py','data/synthetic/src/invoices.csv'])
def test_publication_rejects_raw_private_or_outside_files(path):
    with pytest.raises(ValueError):validate_paths([path])


def test_publication_allows_code_aggregate_csv_and_synthetic_configuration():
    validate_paths(['agent1/models/t1.py','outputs/t1/A_rolling_origin_src.csv','data/synthetic/src/config.json'])
