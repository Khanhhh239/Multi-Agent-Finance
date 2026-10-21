import pandas as pd
from agent1_service.ingest.dates import local_dates


def test_mixed_offsets_are_normalized_to_vietnam_business_date():
    values=pd.Series(['2024-07-01T20:00:00Z','2024-07-02T03:00:00+07:00','2024-07-02'])
    result=local_dates(values,dayfirst=False)
    assert result.eq(pd.Timestamp('2024-07-02')).all()
    assert result.dt.tz is None


def test_vietnam_dayfirst_without_timezone_is_preserved():
    result=local_dates(pd.Series(['03/04/2024','15/03/2024']))
    assert result.tolist()==[pd.Timestamp('2024-04-03'),pd.Timestamp('2024-03-15')]
