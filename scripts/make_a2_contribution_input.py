"""Sinh dữ liệu có nhãn cho demo "Đóng góp huấn luyện" của 3 doanh nghiệp (MPX10, C001, C002) và tệp hướng dẫn.

Mỗi doanh nghiệp có mẫu rủi ro khác nhau nhưng giao nhau, để mô hình chung học được từ cả ba.
Dùng: python scripts/make_a2_contribution_input.py <thư mục đích>
"""
import csv
import hashlib
import random
import sys
from pathlib import Path

PROFILES = {  # P(round_million|rủi ro), P(creator=approver|rủi ro), P(round|ok), P(self|ok), tỷ lệ rủi ro
    'MPX10': (0.80, 0.55, 0.12, 0.10, 0.30),
    'C001': (0.85, 0.30, 0.10, 0.08, 0.28),
    'C002': (0.40, 0.85, 0.12, 0.12, 0.32),
}
GUIDE = """HƯỚNG DẪN DEMO ĐÓNG GÓP HUẤN LUYỆN (3 DOANH NGHIỆP)

Mỗi lần đăng nhập Portal là một doanh nghiệp. Làm lần lượt cho MPX10, C001, C002:

1. Mở http://127.0.0.1:8800, vào "Hồ sơ doanh nghiệp", đặt Mã doanh nghiệp theo bảng dưới, lưu lại.
2. Vào Trợ lý Giám sát (Agent 2) > tab "Đóng góp huấn luyện".
3. Bấm "Chọn tệp CSV" và chọn đúng tệp của doanh nghiệp đó trong thư mục này.
4. Bấm "Mã hóa và gửi lên trạm".

   Mã doanh nghiệp   Tệp
   MPX10             MPX10_du_lieu_co_nhan.csv
   C001              C001_du_lieu_co_nhan.csv
   C002              C002_du_lieu_co_nhan.csv

5. Mở trạm huấn luyện http://127.0.0.1:8890, thấy 3 doanh nghiệp "Đã gửi", bấm "Huấn luyện trên dữ liệu đã mã hóa".
   Trạm chỉ cập nhật mô hình khi kết quả kiểm định (10% dữ liệu giữ lại) tốt hơn phiên bản đang dùng.
6. Quay lại từng doanh nghiệp, tab "Đóng góp huấn luyện", bấm "Đồng bộ mô hình về doanh nghiệp".
   Sau đó bấm "Phân tích dữ liệu mới nhất" ở tab Tổng quan: điểm rủi ro có thêm yếu tố mô hình có nhãn.

Cột trong tệp: record_id, round_million (số tiền tròn triệu 0/1), creator_equals_approver (người lập tự duyệt 0/1), label (1 = có vấn đề, 0 = hợp lệ).
Dữ liệu mô phỏng.
"""


def main():
    dest = Path(sys.argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    for company, prof in PROFILES.items():
        rng = random.Random(int(hashlib.sha256(('fed-sim:' + company).encode()).hexdigest()[:8], 16))
        path = dest / f'{company}_du_lieu_co_nhan.csv'
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['record_id', 'round_million', 'creator_equals_approver', 'label'])
            for i in range(60):
                risk = 1 if rng.random() < prof[4] else 0
                p1, p2 = (prof[0], prof[1]) if risk else (prof[2], prof[3])
                w.writerow([f'{company}-GD-{i + 1:04d}', int(rng.random() < p1), int(rng.random() < p2), risk])
        print(path.name)
    (dest / '00_HUONG_DAN.txt').write_text(GUIDE, encoding='utf-8')


if __name__ == '__main__':
    main()
