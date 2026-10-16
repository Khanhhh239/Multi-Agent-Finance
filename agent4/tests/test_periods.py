import calendar
from datetime import date,timedelta
import pytest
from agent4.engine.periods import resolve_period,previous_period,same_period_last_year,comparable_partial,extract_periods,detect_comparison,PeriodError

AS_OFS = [date(2026,10,14),date(2026,1,1),date(2024,2,29),date(2025,12,31),date(2026,7,1)]
ALIASES = ['today','hôm nay','hiện tại','this_month','tháng này','mtd','last_month','tháng trước',
           'next_month','tháng sau','this_quarter','quý này','last_quarter','quý trước','this_year','năm nay',
           'last_year','năm ngoái','ytd','từ đầu năm đến nay','this_week','tuần này','last_week','tuần trước']

def month_range(y,m):
    return date(y,m,1),date(y,m,calendar.monthrange(y,m)[1])

@pytest.mark.parametrize('as_of',AS_OFS)
@pytest.mark.parametrize('expr',ALIASES)
def test_alias_calendar_boundaries(as_of,expr):
    index = ALIASES.index(expr)
    if index<3:
        expected = (as_of,as_of)
    elif index<6:
        expected = month_range(as_of.year,as_of.month)
    elif index<8:
        prev = as_of.replace(day=1)-timedelta(days=1)
        expected = month_range(prev.year,prev.month)
    elif index<10:
        next_ = month_range(as_of.year,as_of.month)[1]+timedelta(days=1)
        expected = month_range(next_.year,next_.month)
    elif index<14:
        qstart = date(as_of.year,((as_of.month-1)//3)*3+1,1)
        if index>=12:
            prior = qstart-timedelta(days=1)
            qstart = date(prior.year,((prior.month-1)//3)*3+1,1)
        expected = qstart,month_range(qstart.year,qstart.month+2)[1]
    elif index<18:
        year = as_of.year-(index>=16)
        expected = date(year,1,1),date(year,12,31)
    elif index<20:
        expected = date(as_of.year,1,1),as_of
    else:
        start = as_of-timedelta(days=as_of.weekday()+(7 if index>=22 else 0))
        expected = start,start+timedelta(days=6)
    actual = resolve_period(expr,as_of)
    assert (actual.start,actual.end)==expected

@pytest.mark.parametrize('expr,start,end',[
    ('quý IV/2025','2025-10-01','2025-12-31'),('2024-Q1','2024-01-01','2024-03-31'),
    ('2024-02','2024-02-01','2024-02-29'),('6 tháng đầu năm','2026-01-01','2026-06-30'),
    ('6 tháng cuối năm','2026-07-01','2026-12-31'),('3 tháng gần nhất','2026-07-01','2026-09-30'),
    ('30 ngày qua','2026-09-15','2026-10-14'),('15 ngày tới','2026-10-15','2026-10-29'),
    ('2025-06-15..2025-07-15','2025-06-15','2025-07-15'),
])
def test_explicit(expr,start,end):
    p = resolve_period(expr,date(2026,10,14))
    assert (str(p.start),str(p.end))==(start,end)

EXPLICIT = []
for year in (2024,2025,2026):
    for month in range(1,13):
        bounds = month_range(year,month)
        EXPLICIT.extend([(f'{year}-{month:02}',*bounds),(f'tháng {month}/{year}',*bounds)])
    for quarter in range(1,5):
        EXPLICIT.append((f'{year}-Q{quarter}',date(year,(quarter-1)*3+1,1),month_range(year,quarter*3)[1]))

@pytest.mark.parametrize('as_of',AS_OFS)
@pytest.mark.parametrize('expr,start,end',EXPLICIT)
def test_explicit_expressions_ignore_reference_date(as_of,expr,start,end):
    actual = resolve_period(expr,as_of)
    assert (actual.start,actual.end)==(start,end)

@pytest.mark.parametrize('expr',['2026-13','2026-00','2026-02-30','tháng 13','0 ngày tới','0 tháng qua',
                                {'start':'2026-10-15','end':'2026-10-01'},{'start':'2026-02-30','end':'2026-03-01'}])
def test_invalid_is_domain_error(expr):
    with pytest.raises(PeriodError):
        resolve_period(expr,date(2026,10,14))

def test_comparisons():
    as_of = date(2026,10,14)
    current = resolve_period('this_month',as_of)
    prev = previous_period(current)
    assert (str(prev.start),str(prev.end))==('2026-09-01','2026-09-30')
    partial = comparable_partial(current,prev,as_of)
    assert str(partial.end)=='2026-09-14'
    leap = same_period_last_year(resolve_period('2024-02-29',as_of))
    assert str(leap.start)=='2023-02-28'
    assert detect_comparison('so với cùng kỳ năm trước')=='same_period_last_year'
    assert detect_comparison('so với quý trước')=='previous_period'

def test_extract_in_text_order_and_do_not_duplicate():
    hits = extract_periods('So sánh 2026-Q3 và tháng 8/2026 với 2026-07',date(2026,10,14))
    assert [h[1].token for h in hits]==['2026-Q3','2026-08','2026-07']
    assert len(extract_periods('doanh thu cùng kỳ năm trước',date(2026,10,14)))==0
