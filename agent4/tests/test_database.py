from agent4.engine.engine import ExecutionEngine

# Khởi tạo engine trỏ vào database vừa sinh
engine = ExecutionEngine("data/cfo_warehouse.duckdb")

# 1. Thử truy vấn doanh thu thuần quý vừa rồi
res = engine.query("net_revenue", period="last_quarter", compare_to="previous_period")
print(f"Doanh thu: {res['display']} (Tăng/giảm: {res['comparison']['delta_pct_display']})")

# 2. Thử truy vấn công nợ quá hạn
res_ar = engine.query("overdue_receivables", params={"min_days": 30})
print("Nợ quá hạn:", res_ar["summary"])