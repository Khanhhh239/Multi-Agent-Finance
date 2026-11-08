import duckdb
from agent4.datagen.build import _build_budget


def budget(seed,threads):
    with duckdb.connect() as con:
        con.execute(f'SET threads={threads}')
        con.execute('CREATE TABLE budget(year_no INT,month_no INT,branch_code VARCHAR,line_type VARCHAR,cost_category VARCHAR,amount DOUBLE)')
        con.execute("CREATE TABLE v_gl AS SELECT 2025 year_no, 1 month_no, 'HN' branch_code, NULL::VARCHAR cost_category, '5111' account_code, 1000000000.0 credit_amount, 0.0 debit_amount, FALSE is_closing UNION ALL SELECT 2025,1,'HN','LUONG','6422',0.0,100000000.0,FALSE")
        _build_budget(con,seed)
        return con.execute('SELECT * FROM budget ORDER BY ALL').fetchall()


def test_budget_seed_independent_of_threads_and_sensitive_to_seed():
    a=budget(20251,1)
    assert a==budget(20251,4)
    b=budget(71,4)
    assert [r for r in a if r[0]==2025]!=[r for r in b if r[0]==2025]
    assert [r for r in a if r[0]==2026]==[r for r in b if r[0]==2026]
