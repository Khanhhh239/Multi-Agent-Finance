from datetime import date
from agent4.engine.periods import resolve_period

AS_OF=date(2026,10,14)
PHRASES={
 'this_month':['tháng này','tháng hiện tại','tháng 10/2026','2026-10'],
 'last_month':['tháng trước','tháng 9/2026','2026-09','tháng 09/2026'],
 'this_quarter':['quý này','quý 4/2026','2026-Q4','Q4/2026'],
 'last_quarter':['quý trước','quý 3/2026','2026-Q3','Q3/2026'],
 'ytd':['lũy kế từ đầu năm','từ đầu năm đến nay','ytd','2026-01-01..2026-10-14'],
 '2026-Q2':['quý 2/2026','Q2/2026','2026-Q2','quý II/2026'],
 'today':['hôm nay','hiện tại','2026-10-14','bây giờ'],
}


def check_phrases():
    for token,phrases in PHRASES.items():
        gold=resolve_period(token,AS_OF)
        for phrase in phrases:
            actual=resolve_period(phrase,AS_OF)
            assert (actual.start,actual.end)==(gold.start,gold.end),(token,phrase)

