#!/usr/bin/env bash
# Dựng toàn bộ môi trường demo Sổ Son trên máy mới (Windows + Git Bash, hoặc Linux). Chạy từ thư mục gốc repo:
#   bash setup_demo.sh
# Cần: Python 3.12, uv, Ollama, mạng. Thời gian khoảng 40 đến 60 phút, chủ yếu tải mô hình và sinh dữ liệu.
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1

echo "[1/6] Môi trường Python cho bốn agent"
bash setup_env.sh

echo "[2/6] Mô hình Ollama"
for m in qwen3:8b qwen3:4b-instruct-2507-q4_K_M bge-m3 qwen3-embedding:0.6b qwen2.5:0.5b; do ollama pull "$m"; done

echo "[3/6] Bộ dữ liệu Minh Phát MPX10 (kho Agent 4, hóa đơn XML, sao kê, sổ giao dịch)"
D=portal/workspace/datasets/enterprise-x10-v3-full
PY4=agent4/.venv/Scripts/python.exe; [ -x "$PY4" ] || PY4=agent4/.venv/bin/python
if [ ! -f "$D/warehouse.duckdb" ]; then
  "$PY4" data_pipeline/enterprise.py --out "$D"
  "$PY4" data_pipeline/validate.py "$D"
  "$PY4" data_pipeline/export.py "$D"
fi
"$PY4" data_pipeline/demo_inputs.py "$D" portal/workspace/mpx10-demo-input-full || true

echo "[4/6] Agent 3: kho luật (vbpl.vn), vectơ nhúng, mô hình xếp hạng lại"
PY3=$PWD/agent3/.venv/Scripts/python.exe; [ -x "$PY3" ] || PY3=$PWD/agent3/.venv/bin/python
( cd agent3/agent3_tax_compliance
  "$PY3" -m src.lawbase.cli sync
  "$PY3" -m src.lawbase.dense build
  "$PY3" -c "from huggingface_hub import snapshot_download as s; s('AITeamVN/Vietnamese_Reranker', local_dir='models/Vietnamese_Reranker')" )

echo "[5/6] Cấu hình portal"
python - <<'PY'
import json, os
c = json.load(open('portal/config.example.json', encoding='utf-8'))
c['demo_company'] = {'code': 'MPX10', 'tax_code': '0999999905'}
c['agents']['agent4']['env'] = {'AGENT4_DB_PATH': os.path.abspath('portal/workspace/datasets/enterprise-x10-v3-full/warehouse.duckdb')}
json.dump(c, open('portal/config.local.json', 'w', encoding='utf-8'), indent=2)
m = [{'company_id': k, 'role': 'director', 'status': 'active', 'permissions': ['data.import', 'evidence.verify', 'model.fit']} for k in ('MPX10', 'C001', 'C002')]
os.makedirs('portal/workspace', exist_ok=True)
json.dump({'version': 'portal-agent2-access/1.0.0', 'actor_id': 'portal-workspace', 'tenant_id': 'demo', 'status': 'active', 'memberships': m},
          open('portal/workspace/agent2_access.json', 'w', encoding='utf-8'), indent=2)
PY
mkdir -p agent2/.runtime/platform

echo "[6/6] Xong. Chạy: agent2/.venv/Scripts/python.exe -X utf8 portal/server.py --start-all  rồi mở http://127.0.0.1:8800"
echo "Việc làm tay một lần: Hồ sơ doanh nghiệp (MPX10, MST 0999999905), đặt mật khẩu ở Nạp dữ liệu, nạp 4 tệp trong portal/workspace/mpx10-demo-input-full."
