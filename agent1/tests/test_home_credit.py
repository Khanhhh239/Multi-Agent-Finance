import pandas as pd
from agent1.data.real_loaders import home_credit_installments


def test_partial_instalments_do_not_duplicate_scheduled_amount(tmp_path):
    raw = pd.DataFrame({'SK_ID_CURR': [1, 1], 'SK_ID_PREV': [2, 2], 'NUM_INSTALMENT_VERSION': [1, 1],
                         'NUM_INSTALMENT_NUMBER': [3, 3], 'DAYS_INSTALMENT': [-10, -10],
                         'DAYS_ENTRY_PAYMENT': [-12, -5], 'AMT_INSTALMENT': [100., 100.], 'AMT_PAYMENT': [40., 60.]})
    path = tmp_path / 'installments.csv'; raw.to_csv(path, index=False)
    inv, pay = home_credit_installments(path)
    assert len(inv) == 1 and inv.amount_gross.iloc[0] == 100
    assert inv.paid_amount.iloc[0] == 100
    assert inv.paid_date_true.iloc[0] == pd.Timestamp('1999-12-27')
    assert pay.kind.tolist() == ['partial', 'final']
