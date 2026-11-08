import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sprint1'))
from fullweek_journal import HEADER, HEADING, SEPARATOR, normalize


def test_rerun_rows_rejoin_section_seven_without_reformatting_other_work():
    other = '## 8. Sprint 4\n\n- Other agent result.\n\nParagraph.\n'
    first = '| 21/10/2026 08:17 | A | 1s | 2 → 1 | passed |'
    misplaced = '| 21/10/2026 09:42 | B | 2s | 4 → 3 | passed |'
    source = f'Intro\n\n{HEADING}\n\n{HEADER}\n{SEPARATOR}\n\n{first}\n\n{other}{misplaced}\n'
    result = normalize(source)
    assert result.endswith(other)
    assert result.index(misplaced) < result.index('## 8.')
    assert result.count(first) == result.count(misplaced) == 1
    assert normalize(result) == result
