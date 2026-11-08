"""Keep rerun rows in section 7 while preserving other contributors' sections."""
import re

HEADING = '## 7. Chạy lại (agent khác ghi vào đây)'
HEADER = '| Ngày | Job | Thời gian | Số chính trước → sau | Ghi chú |'
SEPARATOR = '|---|---|---|---|---|'


def normalize(text, row=None):
    if HEADING not in text:
        raise ValueError('Missing rerun journal section 7')
    prefix, tail = text.split(HEADING, 1)
    rows = []
    remaining = []
    for line in tail.splitlines(keepends=True):
        if re.match(r'^\| \d{2}/\d{2}/\d{4}(?: |\|)', line):
            rows.append(line.strip())
        else:
            remaining.append(line)
    if row:
        rows.append(row.strip())
    rest = ''.join(remaining)
    next_section = re.search(r'^## ', rest, flags=re.MULTILINE)
    if next_section:
        current, following = rest[:next_section.start()], rest[next_section.start():]
    else:
        current, following = rest, ''
    notes = '\n'.join(line for line in current.splitlines()
                      if line.strip() and line.strip() not in {HEADER, SEPARATOR})
    table = '\n'.join([HEADER, SEPARATOR, *rows])
    return prefix + HEADING + '\n\n' + (notes + '\n\n' if notes else '') + table + '\n\n' + following


def append_row(path, row):
    path.write_text(normalize(path.read_text(encoding='utf-8'), row), encoding='utf-8')
