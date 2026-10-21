"""Isolated P2 sources for web/backup tests, independent of developer datasets."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
from unittest.mock import patch

from sme_fraud.run_p2_controls import prepare, evaluate


_temporary = tempfile.TemporaryDirectory(prefix='sme_p2_tests_')
_root = Path(_temporary.name)
SOURCE, REPORT = _root/'source', _root/'report'
# These are declared synthetic controls. No original SME snapshot is read or
# modified to prepare them; production fingerprint checks remain unchanged.
with redirect_stdout(io.StringIO()), patch('sme_fraud.run_p2_controls.fingerprints', return_value={}):
    prepare(SOURCE)
    _result = evaluate(SOURCE, REPORT)
if not _result['successful']:
    raise AssertionError('Declared P2 fixtures did not match their independent expectations')
