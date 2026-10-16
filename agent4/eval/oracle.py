"""Independent reference calculations from base tables, never engine imports.

Definitions are transcribed from the handoff's accounting descriptions. No
REGISTRY, Term, engine views, or production calculation helpers are used.
Filters accept exact dimension codes (not fuzzy names). All dates are explicit.
"""
from __future__ import annotations
import calendar
import statistics
from datetime import date, timedelta

BASE = """gl_entry g JOIN dim_account a USING(account_key)
LEFT JOIN dim_partner p USING(partner_key)
LEFT JOIN dim_branch b USING(branch_key)
LEFT JOIN dim_employee emp USING(employee_key)
LEFT JOIN dim_department dep USING(department_key)
LEFT JOIN dim_item item USING(item_key)"""
COLUMNS = {"customer": "p.partner_code", "vendor": "p.partner_code", "branch": "b.branch_code",
           "salesperson": "emp.employee_code", "department": "dep.department_code",
           "item": "item.item_code", "product_line": "g.product_line", "cost_category": "g.cost_category"}
INVENTORY = ('151', '152', '153', '154', '155', '156', '157')
CURRENT = ('111','112','113','121','128','131','133','136','138','141', *INVENTORY, '229')
SHORT_DEBT = ('331','333','334','335','338','34111')

def _scalar(con, sql, args=()):
    v = con.execute(sql, args).fetchone()[0]
    return float(v or 0)

def _month(d, offset=0):
    k = d.year * 12 + d.month - 1 + offset
    return date(k // 12, k % 12 + 1, 1)

class Reference:
    def __init__(self, con, start, end, view, filters):
        self.con, self.start, self.end, self.view = con, start, end, view
        self.info = dict(con.execute('SELECT key,value FROM company_info').fetchall())
        self.on = date.fromisoformat(self.info['as_of_date'])
        self.effective = min(end, self.on)
        self.filters = filters or {}

    def where_filters(self):
        clauses, args = [], []
        for key, values in self.filters.items():
            if key not in COLUMNS:
                raise ValueError(f'Unsupported oracle filter: {key}')
            values = values if isinstance(values, list) else [values]
            clauses.append(COLUMNS[key] + ' IN (' + ','.join('?' for _ in values) + ')')
            args.extend(values)
        return (' AND ' + ' AND '.join(clauses) if clauses else ''), args

    def gl(self, prefixes, *, balance=False, side='net', extra='TRUE', start=None, end=None, view=None):
        s, e = start or self.start, end or self.effective
        dates = 'g.posting_date <= ?' if balance else "g.posting_date BETWEEN ? AND ? AND NOT COALESCE(g.is_closing,FALSE) AND COALESCE(g.source_module,'') <> 'OPENING'"
        args = [e] if balance else [s, e]
        cond = '(' + ' OR '.join('a.account_code LIKE ?' for _ in prefixes) + ')'
        args += [v+'%' for v in prefixes]
        fsql, fargs = self.where_filters()
        amount = {'net':'g.debit_amount-g.credit_amount','debit':'g.debit_amount','credit':'g.credit_amount'}[side]
        tax = ' AND g.tax_deductible' if (view or self.view) == 'tax' else ''
        return _scalar(self.con, f'SELECT SUM({amount}) FROM {BASE} WHERE {dates} AND {cond} AND ({extra}){tax}{fsql}', args+fargs)

    def open_ar(self):
        # SQL window allocation rather than the engine's mutable Python FIFO.
        return self.con.execute("""
        WITH paid AS (SELECT invoice_id,SUM(amount) x FROM ar_receipt WHERE receipt_date<=? GROUP BY 1),
        adjusted AS (SELECT invoice_id,SUM(total_amount) x FROM ar_adjustment WHERE adjustment_date<=? GROUP BY 1),
        credits AS (SELECT customer_code,SUM(x) x FROM (
          SELECT customer_code,amount x FROM ar_receipt WHERE invoice_id IS NULL AND receipt_date<=?
          UNION ALL SELECT customer_code,total_amount FROM ar_adjustment WHERE invoice_id IS NULL AND adjustment_date<=?) GROUP BY 1),
        outstanding AS (SELECT i.*,i.total_amount-COALESCE(p.x,0)-COALESCE(a.x,0) remaining
          FROM ar_invoice i LEFT JOIN paid p USING(invoice_id) LEFT JOIN adjusted a USING(invoice_id) WHERE issue_date<=?),
        running AS (SELECT *,SUM(remaining) OVER(PARTITION BY customer_code ORDER BY issue_date,invoice_id) cumulative
          FROM outstanding WHERE remaining>0.5)
        SELECT customer_code,due_date,GREATEST(0,remaining-GREATEST(0,COALESCE(c.x,0)-(cumulative-remaining))) rem
          FROM running LEFT JOIN credits c USING(customer_code)
        UNION ALL SELECT c.customer_code,NULL,-GREATEST(0,c.x-COALESCE(s.x,0))
          FROM credits c LEFT JOIN (SELECT customer_code,SUM(remaining) x FROM outstanding WHERE remaining>0.5 GROUP BY 1) s USING(customer_code)
        """, [self.effective]*5).fetchall()

    def open_ap(self):
        return self.con.execute("""SELECT b.due_date,b.total_amount-COALESCE(p.x,0)
        FROM ap_bill b LEFT JOIN (SELECT bill_id,SUM(amount) x FROM ap_payment WHERE payment_date<=? GROUP BY 1) p USING(bill_id)
        WHERE b.bill_date<=?""", [self.on,self.on]).fetchall()

    def cash_docs(self, start, end):
        # Query raw lines once, classify opposing account sets in Python.
        rows = self.con.execute(f"""SELECT g.journal_id,a.account_code,SUM(g.debit_amount-g.credit_amount)
        FROM {BASE} WHERE g.posting_date BETWEEN ? AND ? AND COALESCE(g.source_module,'')<>'OPENING'
        GROUP BY 1,2""", [start,end]).fetchall()
        docs = {}
        for journal, acc, amount in rows:
            d = docs.setdefault(journal, [0.0,set()])
            if acc.startswith(('111','112')):
                d[0] += float(amount)
            else:
                d[1].add(acc[:3])
        return list(docs.values())

    def value(self, metric):
        g = self.gl
        rev = lambda: -g(('511','521'))
        cost = lambda p: g(p)
        pbt = lambda: -g(('511','521','515','711'))-g(('632','641','642','635','811'))
        profit = lambda: pbt()-g(('821',))
        bal = lambda p: g(p,balance=True)
        simple = {
          'net_revenue': rev, 'gross_revenue': lambda:g(('511',),side='credit'),
          'revenue_deductions':lambda:g(('511',),side='debit')+g(('521',)),
          'goods_revenue':lambda:-g(('5111',)), 'service_revenue':lambda:-g(('5113',)),
          'cogs':lambda:cost(('632',)), 'gross_profit':lambda:rev()-cost(('632',)),
          'selling_expenses':lambda:cost(('641','6421')), 'admin_expenses':lambda:cost(('6422',)),
          'operating_expenses':lambda:cost(('641','642')), 'expense_by_category':lambda:cost(('641','642')),
          'finance_income':lambda:-g(('515',)), 'finance_cost':lambda:cost(('635',)),
          'other_income':lambda:-g(('711',)), 'other_expenses':lambda:cost(('811',)),
          'operating_profit':lambda:rev()-g(('632','641','642','635'))-g(('515',)),
          'profit_before_tax':pbt, 'net_profit':profit, 'income_tax_expense':lambda:g(('821',)),
          'ebitda':lambda:pbt()+g(('635',))+g(('214',),side='credit',extra="g.source_document_type='DEPRECIATION'"),
          'depreciation_expense':lambda:g(('214',),side='credit',extra="g.source_document_type='DEPRECIATION'"),
          'salary_expense':lambda:g(('641','642','154','622','627'),extra="g.cost_category IN ('LUONG','THUONG')"),
          'labor_cost':lambda:g(('641','642','154','622','627'),extra="g.cost_category IN ('LUONG','THUONG','BAOHIEM')"),
          'cash_and_equivalents':lambda:bal(('111','112')), 'term_deposits':lambda:bal(('128',)),
          'ar_balance':lambda:bal(('131',)), 'ar_by_customer':lambda:bal(('131',)), 'ar_by_salesperson':lambda:bal(('131',)),
          'ap_balance':lambda:-bal(('331',)), 'ap_by_vendor':lambda:-bal(('331',)),
          'inventory_value':lambda:bal(INVENTORY), 'tax_payable':lambda:-bal(('333',)), 'debt_balance':lambda:-bal(('341',)),
          'fixed_assets_net':lambda:bal(('211','214')), 'total_assets':lambda:bal(('1','2')),
          'total_liabilities':lambda:-bal(('3',)), 'equity':lambda:-bal(('4','5','6','7','8','9')),
          'working_capital':lambda:bal(CURRENT)+bal(SHORT_DEBT), 'net_cash_flow':lambda:g(('111','112')),
          'taxable_income':pbt, 'deductible_expenses':lambda:g(('632','641','642','635','811')),
        }
        if metric in simple:
            return simple[metric]()
        ratios = {
          'gross_margin_pct':(lambda:rev()-g(('632',)),rev,100),
          'net_margin_pct':(profit,rev,100),
          'current_ratio':(lambda:bal(CURRENT),lambda:-bal(SHORT_DEBT),1),
          'quick_ratio':(lambda:bal(CURRENT)-bal(INVENTORY),lambda:-bal(SHORT_DEBT),1),
          'debt_to_equity':(lambda:-bal(('341',)),lambda:-bal(('4','5','6','7','8','9')),1),
        }
        if metric in ratios:
            num, den, scale = ratios[metric]
            d = den()
            return scale*num()/d if d else None
        if metric in ('dso','dpo','dio'):
            prefixes, sign = {'dso':(('131',),1),'dpo':(('331',),-1),'dio':(INVENTORY,1)}[metric]
            avg = sign*(g(prefixes,balance=True,end=self.start-timedelta(days=1))+bal(prefixes))/2
            if metric == 'dso':
                denominator = g(('131',),side='debit',extra="g.source_document_type='SALES_INVOICE'")
                if not denominator:
                    denominator = -g(('511',))
            elif metric == 'dpo':
                denominator = g(('331',),side='credit',extra="g.source_document_type IN ('PURCHASE_INVOICE','PURCHASE_SERVICE','ASSET_PURCHASE')")
            else:
                denominator = g(('632',))
            return avg/denominator*max((self.effective-self.start).days+1,1) if denominator else None
        if metric == 'cash_conversion_cycle':
            parts = [self.value(k) for k in ('dso','dio','dpo')]
            return parts[0]+parts[1]-parts[2] if None not in parts else None
        if metric == 'dso_actual':
            row = self.con.execute("""SELECT SUM(r.amount*date_diff('day',i.issue_date,r.receipt_date))/NULLIF(SUM(r.amount),0)
            FROM ar_receipt r JOIN ar_invoice i USING(invoice_id) JOIN dim_partner p ON r.customer_code=p.partner_code
            WHERE r.receipt_date BETWEEN ? AND ? AND p.segment<>'RET'""",[self.start,self.effective]).fetchone()
            return float(row[0]) if row[0] is not None else None
        if metric in ('ar_aging','overdue_receivables'):
            return sum(float(rem) for _,due,rem in self.open_ar()
                       if rem and (metric=='ar_aging' or (due is not None and (self.effective-due).days>30)))
        if metric == 'ap_due_soon':
            horizon = self.end if self.start>self.on else self.on+timedelta(days=15)
            return sum(float(rem) for due,rem in self.open_ap() if rem>0.5 and due<=horizon)
        if metric == 'cash_flow_breakdown':
            return sum(amount for amount,_ in self.cash_docs(self.start,self.effective))
        if metric == 'cash_coverage_days':
            out = sum(-a for a,accs in self.cash_docs(self.effective-timedelta(days=89),self.effective)
                      if a<0 and accs and not ('341' in accs and not accs.intersection({'131','331','334','335','338','333'})))
            return bal(('111','112'))/(out/90) if out else None
        if metric == 'cit_estimate':
            return max(0,Reference(self.con,self.start,self.end,'tax',self.filters).value('taxable_income'))*0.2
        if metric == 'mgmt_vs_tax_gap':
            return Reference(self.con,self.start,self.end,'mgmt',self.filters).gl(('6','8'),extra='NOT g.tax_deductible')
        if metric == 'vat_position':
            mgmt = Reference(self.con,self.start,self.end,'mgmt',self.filters)
            tax = Reference(self.con,self.start,self.end,'tax',self.filters)
            return (mgmt.gl(('33311',),side='credit',extra="g.source_document_type='SALES_INVOICE'")
                -mgmt.gl(('33311',),side='debit',extra="g.source_document_type IN ('SALES_RETURN','SALES_REBATE')")
                -tax.gl(('133',),side='debit',extra="g.source_document_type<>'VAT_OFFSET'"))
        if metric == 'payroll_summary':
            return _scalar(self.con,'SELECT SUM(gross_salary+bonus+employer_contribution) FROM payroll WHERE year_month BETWEEN ? AND ?',
                           [self.start.strftime('%Y-%m'),self.effective.strftime('%Y-%m')])
        if metric == 'top_sales_transactions':
            return _scalar(self.con,'SELECT MAX(subtotal) FROM ar_invoice WHERE issue_date BETWEEN ? AND ? AND NOT is_opening',[self.start,self.effective])
        if metric == 'unbalanced_journals':
            return _scalar(self.con,"""SELECT COUNT(*) FROM (SELECT journal_id FROM gl_entry WHERE posting_date BETWEEN ? AND ?
            GROUP BY 1 HAVING SUM(debit_amount)<>SUM(credit_amount))""",[self.start,self.effective])
        if metric == 'expense_spikes':
            previous = Reference(self.con,_month(self.start,-3),_month(self.start)-timedelta(days=1),'mgmt',self.filters)
            current = Reference(self.con,self.start,self.end,'mgmt',self.filters)
            categories = [r[0] for r in self.con.execute('SELECT cost_category FROM dim_cost_category').fetchall()]
            full = calendar.monthrange(self.start.year,self.start.month)[1] if self.start.day==1 and self.end.day==calendar.monthrange(self.end.year,self.end.month)[1] and self.start.month==self.end.month else (self.effective-self.start).days+1
            weight = min(1,((self.effective-self.start).days+1)/full)
            return max((current.gl(('641','642'),extra=f"g.cost_category='{c}'")-previous.gl(('641','642'),extra=f"g.cost_category='{c}'")/3*weight for c in categories),default=0)
        if metric == 'budget_vs_actual':
            budget = 0.0
            d = _month(self.start)
            while d<=self.effective:
                last = date(d.year,d.month,calendar.monthrange(d.year,d.month)[1])
                fraction = ((min(last,self.effective)-max(d,self.start)).days+1)/last.day
                budget += _scalar(self.con,"SELECT SUM(amount) FROM budget WHERE year_no=? AND month_no=? AND line_type='REVENUE'",[d.year,d.month])*fraction
                d = last+timedelta(days=1)
            return -g(('511',),view='mgmt')-budget
        if metric == 'unusual_account_movements':
            return self.unusual()
        if metric == 'upcoming_obligations':
            return self.obligations()
        raise KeyError(f'Oracle missing: {metric}')

    def unusual(self):
        months = [_month(self.effective,-k).strftime('%Y-%m') for k in range(7)]
        data = self.con.execute(f"""SELECT a.account_code,strftime(g.posting_date,'%Y-%m'),SUM(g.debit_amount),SUM(g.credit_amount)
        FROM {BASE} WHERE g.posting_date BETWEEN ? AND ? AND NOT g.is_closing AND COALESCE(g.source_module,'')<>'OPENING' GROUP BY 1,2""",
        [_month(self.effective,-6),self.effective]).fetchall()
        series = {}
        for acc,ym,dr,cr in data:
            series.setdefault(acc,{})[ym] = (float(dr),float(cr))
        count = 0
        for values in series.values():
            for side in (0,1):
                history = [values.get(m,(0,0))[side] for m in months[1:]]
                mu = statistics.mean(history)
                sd = statistics.pstdev(history) or max(mu*.1,1)
                delta = values.get(months[0],(0,0))[side]-mu
                count += abs(delta/sd)>=2.5 and abs(delta)>=50_000_000
        return float(count)

    def obligations(self):
        on, horizon = self.on,max(self.on,self.end)
        ref = Reference(self.con,on,on,'mgmt',{})
        owed = {a:-ref.gl((a,),balance=True) for a in ('33311','3334','3335','334','3382','3383','3384','3385')}
        total = sum(float(rem) for due,rem in self.open_ap() if rem>0.5 and due<=horizon)
        total += sum(max(0,owed[a]) for a in ('33311','3334','3335','334'))
        total += max(0,sum(owed[a] for a in ('3382','3383','3384','3385')))
        salary = _scalar(self.con,"SELECT SUM(net_pay) FROM payroll WHERE year_month=(SELECT MAX(year_month) FROM payroll)")
        paydays = sum((on+timedelta(days=k)).day==5 for k in range((horizon-on).days+1))
        if owed['334'] < salary*.5:
            total += salary*paydays
        total += _scalar(self.con,'SELECT SUM(principal) FROM loan_schedule WHERE due_date>? AND due_date<=?',[on,horizon])
        interest = ref.gl(('635',),start=on-timedelta(days=89),end=on)/3*max(1,round((horizon-on).days/30))
        return total+max(0,interest)

def oracle(con, metric: str, start: date, end: date, view='mgmt', filters=None):
    unsupported_filtered = {'ar_aging','overdue_receivables','dso_actual','ap_due_soon','upcoming_obligations',
                            'cash_flow_breakdown','cash_coverage_days','payroll_summary','top_sales_transactions',
                            'unbalanced_journals','budget_vs_actual','unusual_account_movements'}
    if filters and metric in unsupported_filtered:
        raise ValueError(f'Filtered independent oracle not implemented for {metric}')
    return Reference(con,start,end,view,filters).value(metric)
