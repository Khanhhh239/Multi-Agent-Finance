import io
import zipfile

import pytest

from agent2.service import extract_csv_archive


@pytest.mark.parametrize('filename', ['../outside.csv', '/absolute.csv', '//server/share/file.csv',
                                     '\\\\server\\share\\file.csv', 'C:device.csv', 'CON.csv',
                                     'folder.. /transactions.csv', 'folder/../transactions.csv'])
def test_windows_paths_rejected_before_any_output(tmp_path, filename):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr(filename, 'a,b\n1,2\n')
    with pytest.raises(ValueError, match='unsafe'):
        extract_csv_archive(payload.getvalue(), tmp_path)
    assert not list(tmp_path.iterdir())
