"""Reuse frozen v6 as-of features with a private empty-receipt-history fix."""
import pandas as pd
from experiments.t1_competing_v6.features import V6SnapshotBuilder, model_view


class SnapshotBuilder(V6SnapshotBuilder):
    def snapshot(self,T,visible_from=None,firms=None):
        t = pd.Timestamp(T)
        inv = self.inv
        open_rows = inv.issue_date.le(t) & ~(inv.label_date.notna() & inv.label_date.le(t))
        open_rows &= ~(inv.writeoff_date.notna() & inv.writeoff_date.le(t))
        open_rows &= ~(inv.credit_note_date.le(t) & inv.credit_note.ge(inv.amount_gross-1))
        if firms is not None:
            open_rows &= inv.firm_id.isin(firms)
        if visible_from is not None:
            open_rows &= inv.issue_date.ge(pd.Timestamp(visible_from))
        pay = self.pay
        no_known_open_receipt = pay is not None and not (pay.pdate.le(t) & pay.invoice_id.isin(inv.loc[open_rows,"invoice_id"])).any()
        if no_known_open_receipt:
            self.pay = None
        try:
            result = super().snapshot(t,visible_from=visible_from,firms=firms)
        finally:
            self.pay = pay
        if no_known_open_receipt and len(result):
            result["paid_frac_so_far"] = 0.
        return result
