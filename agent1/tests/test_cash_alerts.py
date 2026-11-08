import pandas as pd
from agent1.eval.alerts import choose_threshold,event_metrics


def test_alert_threshold_uses_miss_cost_tradeoff():
    y=[0,0,1,1];p=[.1,.4,.3,.8]
    low,_=choose_threshold(y,p,2)
    high,_=choose_threshold(y,p,10)
    assert high<=low


def test_event_metrics_do_not_count_every_negative_day_as_an_event():
    dates=pd.date_range('2024-01-01',periods=120)
    cash=pd.DataFrame({'firm_id':['f']*120,'date':dates,'balance':[100.]*60+[-1.]*60})
    forecast=pd.DataFrame({'firm_id':['f']*12,'cutoff':pd.date_range('2024-01-01',periods=12,freq='7D'),'p13':[.9]*12})
    out=event_metrics(forecast,cash,threshold=.5)
    assert out['n_events']==1
    assert out['detected_at_least_4w']==1
