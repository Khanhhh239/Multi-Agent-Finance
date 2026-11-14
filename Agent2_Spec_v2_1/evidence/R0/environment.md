# Môi trường thực tế — R0

- Repo: `D:\agent22`, nhánh `platform-Khanh`, commit `3cae5a3bba535694235179651b2e5daee8237656`; working tree có thay đổi cũ chưa commit.
- Agent2: `D:\agent22\agent2`. Bản nguồn cũ và dữ liệu: `D:\agent22_legacy_20261110\agent2`. `.venv` giữ tại vị trí cũ.
- Python 3.12.7; stdlib HTTP, NumPy/SciPy/scikit-learn/NetworkX/joblib. Các phiên bản thực đo ở environment.json.
- SQLite cũ có 41 bảng. Web, import, case/review, model registry và thông báo cũ được lưu trữ; core-only chưa có DB nghiệp vụ mới.
- Lockfile cũ khác môi trường đang chạy; lockfile mới ghi đúng các package core đã đo. Không đổi stack.
- Baseline cũ: 357 tests, exit 0, skip 0. Candidate: 363 tests, exit 0, skip 0; logs và JSON đi kèm.
- Tính năng portal khác không bị sửa; launcher Agent2 còn trang trạng thái loopback, API cũ trả 410, pipeline_ready=false.
- D-01 đã có dữ kiện kỹ thuật, chưa ghi người duyệt giả. D-10/D-18/D-19 chưa chốt; dữ liệu thật/production chưa được mở.
