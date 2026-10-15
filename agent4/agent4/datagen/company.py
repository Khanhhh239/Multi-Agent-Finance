"""Master data of the synthetic company "CTCP Thương mại & Dịch vụ Minh Phát".

The company is fictional.  It is a medium-sized Vietnamese SME (TT133 regime)
that distributes IT / office equipment, sells consumables and provides
maintenance services from three branches.  Every number below is chosen to
look like a real mid-market distributor:

* ~110–150 tỷ đồng revenue per year, ~95 employees, 3 branches.
* Distribution gross margin 15–22% on goods, ~50% on services.
* Customer concentration: the top 10 customers bring ~45% of revenue.
* Payment terms 0/30/45/60 days with segment-specific lateness.

Accounting rules follow Thông tư 133/2016/TT-BTC: no account 521 (sales
deductions are debited to 511), selling / admin expenses are 6421 / 6422,
bad-debt provision is 2293.  Payroll contributions use the 2025–2026 rates
(employer 17.5% BHXH + 3% BHYT + 1% BHTN + 2% KPCĐ; employee 8% + 1.5% + 1%).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

COMPANY = {
    "name": "Công ty Cổ phần Thương mại và Dịch vụ Minh Phát",
    "short_name": "Minh Phát",
    "tax_id": "0109876543",
    "regime": "TT133/2016/TT-BTC",
    "currency": "VND",
    "fiscal_year_start_month": 1,
    "cit_rate": 0.20,
}

# (code, name, account_type, normal_balance, parent)
# account_type is the reporting class used by the balance sheet / P&L.
ACCOUNTS: list[tuple[str, str, str, str, str | None]] = [
    ("111", "Tiền mặt", "ASSET", "D", None),
    ("1111", "Tiền mặt - VND", "ASSET", "D", "111"),
    ("112", "Tiền gửi ngân hàng", "ASSET", "D", None),
    ("11211", "Tiền gửi VND - Ngân hàng An Bình Phát (TK 0011)", "ASSET", "D", "112"),
    ("11212", "Tiền gửi VND - Ngân hàng Kỹ Thương Việt (TK 1903)", "ASSET", "D", "112"),
    ("128", "Đầu tư nắm giữ đến ngày đáo hạn", "ASSET", "D", None),
    ("1281", "Tiền gửi có kỳ hạn", "ASSET", "D", "128"),
    ("131", "Phải thu của khách hàng", "ASSET", "D", None),
    ("133", "Thuế GTGT được khấu trừ", "ASSET", "D", None),
    ("1331", "Thuế GTGT được khấu trừ của hàng hóa, dịch vụ", "ASSET", "D", "133"),
    ("138", "Phải thu khác", "ASSET", "D", None),
    ("1388", "Phải thu khác", "ASSET", "D", "138"),
    ("141", "Tạm ứng", "ASSET", "D", None),
    ("153", "Công cụ, dụng cụ", "ASSET", "D", None),
    ("154", "Chi phí sản xuất, kinh doanh dở dang", "ASSET", "D", None),
    ("156", "Hàng hóa", "ASSET", "D", None),
    ("1561", "Giá mua hàng hóa", "ASSET", "D", "156"),
    ("211", "Tài sản cố định", "ASSET", "D", None),
    ("2111", "TSCĐ hữu hình", "ASSET", "D", "211"),
    ("214", "Hao mòn tài sản cố định", "ASSET", "C", None),
    ("2141", "Hao mòn TSCĐ hữu hình", "ASSET", "C", "214"),
    ("229", "Dự phòng tổn thất tài sản", "ASSET", "C", None),
    ("2293", "Dự phòng phải thu khó đòi", "ASSET", "C", "229"),
    ("242", "Chi phí trả trước", "ASSET", "D", None),
    ("331", "Phải trả cho người bán", "LIABILITY", "C", None),
    ("333", "Thuế và các khoản phải nộp Nhà nước", "LIABILITY", "C", None),
    ("33311", "Thuế GTGT đầu ra", "LIABILITY", "C", "333"),
    ("3334", "Thuế thu nhập doanh nghiệp", "LIABILITY", "C", "333"),
    ("3335", "Thuế thu nhập cá nhân", "LIABILITY", "C", "333"),
    ("3338", "Thuế khác (môn bài)", "LIABILITY", "C", "333"),
    ("334", "Phải trả người lao động", "LIABILITY", "C", None),
    ("335", "Chi phí phải trả", "LIABILITY", "C", None),
    ("338", "Phải trả, phải nộp khác", "LIABILITY", "C", None),
    ("3382", "Kinh phí công đoàn", "LIABILITY", "C", "338"),
    ("3383", "Bảo hiểm xã hội", "LIABILITY", "C", "338"),
    ("3384", "Bảo hiểm y tế", "LIABILITY", "C", "338"),
    ("3385", "Bảo hiểm thất nghiệp", "LIABILITY", "C", "338"),
    ("3388", "Phải trả, phải nộp khác", "LIABILITY", "C", "338"),
    ("341", "Vay và nợ thuê tài chính", "LIABILITY", "C", None),
    ("3411", "Các khoản đi vay", "LIABILITY", "C", "341"),
    ("34111", "Vay ngắn hạn", "LIABILITY", "C", "3411"),
    ("34112", "Vay dài hạn", "LIABILITY", "C", "3411"),
    ("411", "Vốn đầu tư của chủ sở hữu", "EQUITY", "C", None),
    ("4111", "Vốn góp của chủ sở hữu", "EQUITY", "C", "411"),
    ("421", "Lợi nhuận sau thuế chưa phân phối", "EQUITY", "C", None),
    ("4211", "LNST chưa phân phối năm trước", "EQUITY", "C", "421"),
    ("4212", "LNST chưa phân phối năm nay", "EQUITY", "C", "421"),
    ("511", "Doanh thu bán hàng và cung cấp dịch vụ", "REVENUE", "C", None),
    ("5111", "Doanh thu bán hàng hóa", "REVENUE", "C", "511"),
    ("5113", "Doanh thu cung cấp dịch vụ", "REVENUE", "C", "511"),
    ("515", "Doanh thu hoạt động tài chính", "REVENUE", "C", None),
    ("632", "Giá vốn hàng bán", "EXPENSE", "D", None),
    ("635", "Chi phí tài chính", "EXPENSE", "D", None),
    ("642", "Chi phí quản lý kinh doanh", "EXPENSE", "D", None),
    ("6421", "Chi phí bán hàng", "EXPENSE", "D", "642"),
    ("6422", "Chi phí quản lý doanh nghiệp", "EXPENSE", "D", "642"),
    ("711", "Thu nhập khác", "REVENUE", "C", None),
    ("811", "Chi phí khác", "EXPENSE", "D", None),
    ("821", "Chi phí thuế thu nhập doanh nghiệp", "EXPENSE", "D", None),
    ("911", "Xác định kết quả kinh doanh", "CLOSING", "C", None),
]
POSTABLE_PARENTS = {"131", "141", "153", "154", "242", "331", "334", "335", "515",
                    "632", "635", "711", "811", "821", "911"}

BRANCHES = [
    # code, name, region, revenue share, minimum-wage region
    ("HN", "Trụ sở Hà Nội", "Miền Bắc", 0.46),
    ("HCM", "Chi nhánh TP. Hồ Chí Minh", "Miền Nam", 0.39),
    ("DN", "Chi nhánh Đà Nẵng", "Miền Trung", 0.15),
]

# code, name, expense account (TT133), headcount by branch {HN, HCM, DN}, salary band (triệu)
DEPARTMENTS = [
    ("BGD", "Ban Giám đốc", "6422", {"HN": 3, "HCM": 1, "DN": 1}, (35, 60)),
    ("KD", "Phòng Kinh doanh", "6421", {"HN": 12, "HCM": 11, "DN": 5}, (11, 20)),
    ("MKT", "Phòng Marketing", "6421", {"HN": 4, "HCM": 2, "DN": 0}, (12, 20)),
    ("KT", "Phòng Kỹ thuật - Dịch vụ", "154", {"HN": 9, "HCM": 8, "DN": 4}, (12, 20)),
    ("KHO", "Kho vận", "6421", {"HN": 6, "HCM": 5, "DN": 3}, (8, 11)),
    ("TCKT", "Phòng Tài chính - Kế toán", "6422", {"HN": 6, "HCM": 2, "DN": 1}, (12, 22)),
    ("HCNS", "Phòng Hành chính - Nhân sự", "6422", {"HN": 4, "HCM": 2, "DN": 1}, (9, 15)),
]

# Expense items ("khoản mục chi phí") as in MISA AMIS / Fast — this is what a
# CEO means by "chi phí gồm những khoản nào".
COST_CATEGORIES = [
    ("LUONG", "Lương và phụ cấp"),
    ("BAOHIEM", "Bảo hiểm & KPCĐ (DN đóng)"),
    ("THUONG", "Thưởng"),
    ("THUE_MB", "Thuê mặt bằng"),
    ("DIEN_NUOC", "Điện, nước"),
    ("VIENTHONG", "Viễn thông, Internet"),
    ("MARKETING", "Quảng cáo, marketing"),
    ("VANCHUYEN", "Vận chuyển, giao hàng"),
    ("CONGTAC", "Công tác phí"),
    ("TIEPKHACH", "Tiếp khách"),
    ("KHAUHAO", "Khấu hao TSCĐ"),
    ("PHANMEM", "Phần mềm, dịch vụ CNTT"),
    ("VPP", "Văn phòng phẩm"),
    ("BAOHIEM_TS", "Bảo hiểm tài sản, xe"),
    ("PHI_NH", "Phí ngân hàng"),
    ("DUPHONG", "Dự phòng nợ khó đòi"),
    ("VATTU_DV", "Vật tư phục vụ dịch vụ"),
    ("THUE_PHI", "Thuế, phí, lệ phí"),
    ("KHAC", "Chi phí khác"),
]

PRODUCT_LINES = [
    ("IT", "Thiết bị CNTT"),
    ("OFF", "Thiết bị văn phòng"),
    ("CON", "Vật tư tiêu hao"),
    ("SVC", "Dịch vụ kỹ thuật"),
]


@dataclass
class ItemSpec:
    code: str
    name: str
    line: str
    unit: str
    list_price: float  # VND, before VAT
    cost_ratio: float  # purchase cost / list price
    vat_class: str  # "STD" (10% → 8% when the reduction applies) or "IT10" (excluded until 2025-07)
    is_service: bool = False


def _items() -> list[ItemSpec]:
    it = [
        ("LAP-DL5440", "Laptop Dell Latitude 5440 i5/16GB/512GB", 23_900_000, 0.84),
        ("LAP-DL7450", "Laptop Dell Latitude 7450 Ultra7/32GB", 41_500_000, 0.85),
        ("LAP-HP840", "Laptop HP EliteBook 840 G11", 32_800_000, 0.84),
        ("LAP-HP250", "Laptop HP 250 G10 i5", 15_600_000, 0.83),
        ("LAP-LN-T14", "Laptop Lenovo ThinkPad T14 Gen 5", 29_400_000, 0.84),
        ("LAP-LN-E14", "Laptop Lenovo ThinkPad E14 Gen 6", 18_900_000, 0.83),
        ("LAP-AS-B1", "Laptop Asus ExpertBook B1", 14_200_000, 0.82),
        ("PC-DL-OPT", "Máy tính để bàn Dell OptiPlex 7010", 17_800_000, 0.83),
        ("PC-HP-PRO", "Máy tính để bàn HP Pro Tower 400", 14_900_000, 0.82),
        ("PC-LN-M70", "Máy tính để bàn Lenovo ThinkCentre M70s", 15_900_000, 0.83),
        ("WS-DL-3680", "Máy trạm Dell Precision 3680", 48_000_000, 0.86),
        ("MON-DL-24", "Màn hình Dell P2425H 24 inch", 4_350_000, 0.80),
        ("MON-DL-27", "Màn hình Dell U2724D 27 inch QHD", 9_900_000, 0.81),
        ("MON-LG-27", "Màn hình LG 27UL550 4K", 7_200_000, 0.80),
        ("MON-SS-22", "Màn hình Samsung 22 inch FHD", 2_450_000, 0.78),
        ("SRV-DL-R660", "Máy chủ Dell PowerEdge R660xs", 168_000_000, 0.88),
        ("SRV-DL-T150", "Máy chủ Dell PowerEdge T150", 42_000_000, 0.87),
        ("SRV-HP-DL380", "Máy chủ HPE ProLiant DL380 Gen11", 215_000_000, 0.88),
        ("NAS-SYN-923", "Thiết bị lưu trữ Synology DS923+", 16_800_000, 0.82),
        ("NET-CS-2960", "Switch Cisco Catalyst 1000 24 port", 12_600_000, 0.82),
        ("NET-FG-60F", "Tường lửa Fortinet FortiGate 60F", 19_800_000, 0.80),
        ("NET-UBQ-AP", "Bộ phát Wifi Ubiquiti UniFi U6 Pro", 4_100_000, 0.76),
        ("NET-DT-RT", "Router Draytek Vigor 2927", 6_300_000, 0.78),
        ("UPS-APC-3K", "Bộ lưu điện APC Smart-UPS 3000VA", 24_500_000, 0.83),
        ("UPS-APC-1K", "Bộ lưu điện APC 1000VA", 5_400_000, 0.79),
        ("SW-MS365", "Bản quyền Microsoft 365 Business Std (năm)", 3_150_000, 0.88),
        ("SW-WIN11", "Bản quyền Windows 11 Pro", 4_800_000, 0.86),
        ("SW-KAS", "Phần mềm diệt virus Kaspersky Endpoint (năm)", 650_000, 0.70),
        ("ACC-KB-LOGI", "Bộ bàn phím chuột Logitech MK295", 690_000, 0.72),
        ("ACC-HD-SS1T", "Ổ cứng SSD Samsung 990 Pro 1TB", 3_100_000, 0.80),
        ("ACC-RAM-16", "RAM DDR5 16GB Kingston", 1_650_000, 0.79),
        ("ACC-DOCK-DL", "Dock Dell WD19S", 5_200_000, 0.80),
        ("ACC-WEB-LOGI", "Webcam Logitech C920", 1_890_000, 0.75),
        ("ACC-HS-JAB", "Tai nghe Jabra Evolve2 40", 2_750_000, 0.76),
        ("CAM-HIK-IP", "Camera IP Hikvision 4MP", 1_950_000, 0.74),
        ("CAM-HIK-NVR", "Đầu ghi Hikvision NVR 16 kênh", 6_900_000, 0.78),
        ("RACK-42U", "Tủ rack 42U", 13_500_000, 0.80),
        ("CBL-CAT6", "Cáp mạng Cat6 AMP (thùng 305m)", 2_850_000, 0.74),
    ]
    off = [
        ("PRN-HP-M404", "Máy in HP LaserJet Pro M404dn", 8_900_000, 0.81),
        ("PRN-HP-M479", "Máy in màu HP Color LaserJet M479fdw", 16_500_000, 0.82),
        ("PRN-CN-2900", "Máy in Canon LBP 2900", 3_450_000, 0.79),
        ("PRN-CN-6030", "Máy in Canon LBP 6030", 2_890_000, 0.78),
        ("PRN-EP-L3250", "Máy in phun Epson L3250", 4_250_000, 0.80),
        ("PRN-BR-L2366", "Máy in Brother HL-L2366DW", 3_990_000, 0.79),
        ("CPY-RC-2701", "Máy photocopy Ricoh IM 2702", 58_000_000, 0.83),
        ("CPY-TS-2523", "Máy photocopy Toshiba e-STUDIO 2523A", 36_500_000, 0.82),
        ("CPY-CN-2425", "Máy photocopy Canon iR 2425", 41_800_000, 0.83),
        ("SCN-FJ-7160", "Máy scan Fujitsu fi-7160", 22_400_000, 0.82),
        ("SCN-CN-180", "Máy scan Canon DR-C230", 9_800_000, 0.80),
        ("PJT-EP-X51", "Máy chiếu Epson EB-X51", 10_900_000, 0.81),
        ("PJT-VS-PA", "Máy chiếu ViewSonic PA503X", 8_200_000, 0.80),
        ("PJT-SCR-120", "Màn chiếu điện 120 inch", 3_200_000, 0.74),
        ("SHR-GBC", "Máy hủy tài liệu GBC ShredMaster", 6_900_000, 0.78),
        ("TEL-PNS-IP", "Điện thoại IP Panasonic KX-HDV130", 1_750_000, 0.74),
        ("TEL-YLK-T54", "Điện thoại IP Yealink T54W", 4_900_000, 0.78),
        ("TMC-RJ-F18", "Máy chấm công vân tay Ronald Jack", 3_600_000, 0.76),
        ("MTG-LOGI-RM", "Thiết bị họp trực tuyến Logitech Rally Bar", 72_000_000, 0.85),
        ("TV-SS-65", "Màn hình tương tác 65 inch", 39_500_000, 0.83),
    ]
    con = [
        ("TNR-HP-76A", "Mực in HP 76A chính hãng", 2_650_000, 0.80),
        ("TNR-HP-26A", "Mực in HP 26A chính hãng", 2_350_000, 0.80),
        ("TNR-CN-303", "Mực in Canon 303", 1_650_000, 0.78),
        ("TNR-CN-325", "Mực in Canon 325", 1_450_000, 0.77),
        ("TNR-BR-2385", "Mực in Brother TN-2385", 1_250_000, 0.76),
        ("INK-EP-003", "Mực in Epson 003 (bộ 4 màu)", 520_000, 0.72),
        ("TNR-RC-2702", "Mực photocopy Ricoh IM 2702", 1_950_000, 0.75),
        ("TNR-TS-2523", "Mực photocopy Toshiba T-2323", 1_380_000, 0.74),
        ("DRM-RC-2702", "Cụm trống Ricoh IM 2702", 4_600_000, 0.78),
        ("PAP-A4-DD", "Giấy A4 Double A 80gsm (thùng 5 ram)", 455_000, 0.82),
        ("PAP-A4-IK", "Giấy A4 IK Plus 70gsm (thùng 5 ram)", 365_000, 0.81),
        ("PAP-A3-DD", "Giấy A3 Double A 80gsm (thùng 5 ram)", 905_000, 0.82),
        ("PAP-NOTE", "Giấy note, sổ, bìa (combo VPP)", 280_000, 0.70),
        ("BAT-UPS-12V", "Ắc quy UPS 12V 9Ah", 520_000, 0.75),
        ("CLN-KIT", "Bộ vệ sinh thiết bị", 180_000, 0.62),
        ("RBN-EPS-LQ", "Băng mực Epson LQ-310", 145_000, 0.68),
    ]
    out: list[ItemSpec] = []
    for code, name, price, ratio in it:
        unit = "bộ" if code.startswith(("SW-", "ACC-KB")) else ("thùng" if code.startswith("CBL") else "cái")
        out.append(ItemSpec(code, name, "IT", unit, price, ratio, "IT10"))
    for code, name, price, ratio in off:
        out.append(ItemSpec(code, name, "OFF", "cái", price, ratio, "STD"))
    for code, name, price, ratio in con:
        unit = "thùng" if code.startswith("PAP-A") else "hộp"
        out.append(ItemSpec(code, name, "CON", unit, price, ratio, "STD"))
    svc = [
        ("DV-BT-MAYIN", "Dịch vụ bảo trì máy in, photocopy (tháng)", 4_800_000),
        ("DV-BT-IT", "Dịch vụ bảo trì hệ thống CNTT (tháng)", 12_500_000),
        ("DV-HD-IT", "Dịch vụ hỗ trợ kỹ thuật tại chỗ (helpdesk, tháng)", 18_000_000),
        ("DV-LD-MANG", "Dịch vụ thi công, lắp đặt hệ thống mạng", 35_000_000),
        ("DV-LD-CAM", "Dịch vụ lắp đặt camera an ninh", 15_000_000),
        ("DV-CTHUE-MP", "Dịch vụ cho thuê máy photocopy (tháng)", 3_600_000),
        ("DV-SUA", "Dịch vụ sửa chữa thiết bị (theo lần)", 1_800_000),
        ("DV-TV-CDS", "Dịch vụ tư vấn chuyển đổi số", 60_000_000),
    ]
    for code, name, price in svc:
        out.append(ItemSpec(code, name, "SVC", "gói", price, 0.0, "STD", is_service=True))
    return out


ITEMS = _items()

# VAT: Nghị quyết/Nghị định giảm 2% GTGT (10% → 8%).  H1-2025 (NĐ 180/2024)
# excluded IT products; from 2025-07-01 to 2026-12-31 (NĐ 174/2025) the
# reduction also covers them.  Services here are ordinary 10% services.
VAT_REDUCTION_START = date(2025, 1, 1)
VAT_REDUCTION_IT_START = date(2025, 7, 1)
VAT_REDUCTION_END = date(2026, 12, 31)


def vat_rate(vat_class: str, on: date) -> float:
    if not (VAT_REDUCTION_START <= on <= VAT_REDUCTION_END):
        return 0.10
    if vat_class == "IT10" and on < VAT_REDUCTION_IT_START:
        return 0.10
    return 0.08


# Payroll contribution rates (Luật BHXH 2024, unchanged for 2025–2026).
EMPLOYER_RATES = {"3383": 0.175, "3384": 0.03, "3385": 0.01, "3382": 0.02}
EMPLOYEE_RATES = {"3383": 0.08, "3384": 0.015, "3385": 0.01}
MIN_WAGE_REGION_I = {2025: 4_960_000, 2026: 5_310_000}  # NĐ 74/2024, NĐ 293/2025
SOCIAL_INSURANCE_CAP = 46_800_000  # 20 × mức tham chiếu 2.340.000 (cap on contribution base)

# Customer segments: share of customers, order size multiplier, terms, payment behaviour.
@dataclass(frozen=True)
class Segment:
    code: str
    label: str
    terms: tuple[int, ...]
    # payment delay after due date, in days: (probability on-time, mean late days)
    on_time_prob: float
    late_mean_days: float
    lines: tuple[str, ...]


SEGMENTS = {
    "ENT": Segment("ENT", "Doanh nghiệp lớn", (45, 60), 0.55, 18, ("IT", "OFF", "CON", "SVC")),
    "SME": Segment("SME", "Doanh nghiệp SME", (30,), 0.62, 12, ("IT", "OFF", "CON", "SVC")),
    "GOV": Segment("GOV", "Cơ quan nhà nước / trường học", (60,), 0.35, 38, ("IT", "OFF", "CON")),
    "DLR": Segment("DLR", "Đại lý bán lại", (15, 30), 0.70, 8, ("CON", "OFF", "IT")),
    "RET": Segment("RET", "Khách lẻ", (0,), 1.0, 0, ("CON", "OFF", "IT")),
}


@dataclass
class Partner:
    code: str
    name: str
    ptype: str  # CUSTOMER | VENDOR
    tax_id: str | None
    branch: str
    segment: str | None = None
    terms: int = 30
    weight: float = 1.0
    behaviour: str = "NORMAL"  # NORMAL | CHRONIC_LATE | PROMPT | DISTRESSED
    category: str | None = None  # vendor category
    salesperson: str | None = None
    lines: tuple[str, ...] = field(default_factory=tuple)
    credit_limit: float = 0.0
    province: str = ""


CUSTOMER_PREFIX = ["Công ty TNHH", "Công ty Cổ phần", "Công ty TNHH MTV", "Tập đoàn", "Công ty CP"]
CUSTOMER_STEMS = [
    "Xây dựng Hoàng Long", "Dược phẩm Phúc An", "Logistics Tân Cảng Xanh", "Thép Việt Hưng",
    "Thực phẩm Sao Khuê", "Ô tô Thành Đạt", "Bất động sản Kim Ngân", "Nhựa Bình Minh Phát",
    "May mặc Phương Nam", "Điện tử Hòa Phú", "Bảo hiểm An Tín", "Giáo dục Trí Việt",
    "Khách sạn Biển Ngọc", "Bệnh viện Đa khoa Hồng Đức", "Ngân hàng số Lạc Việt (khối VP)",
    "Chứng khoán Đông Á Mới", "Cơ khí Trường Sơn", "Xi măng Đèo Cả Phát", "Nước giải khát Suối Mát",
    "Thủy sản Cà Mau Xanh", "Cao su Đồng Nai Mới", "Du lịch Hành Trình Việt", "Kiến trúc Nhà Đẹp",
    "In ấn Bao bì Tân Tiến", "Phân bón Mùa Vàng", "Hóa chất Đức Giang Mới", "Gỗ nội thất An Khang Phát",
    "Vận tải Bắc Nam Express", "Siêu thị Gia Đình", "Nông sản Tây Nguyên Xanh", "Truyền thông Đất Việt",
    "Kế toán Kiểm toán Chuẩn Việt", "Luật Hợp Danh Minh Chính", "Thiết bị Y tế Thiên Phúc",
    "Năng lượng Mặt Trời Đông Dương", "Điện lạnh Bách Khoa", "Phần mềm Sóng Việt", "Công nghệ Viettech Số",
    "Nhà hàng Ẩm thực Ba Miền", "Tư vấn Đầu tư Tầm Nhìn", "Bao bì Nhựa Rạng Đông", "Gạch men Hoàn Mỹ",
    "Sữa Thảo Nguyên", "Dệt may Hà Thành", "Đóng tàu Sông Hàn", "Cảng biển Liên Chiểu Mới",
    "Vật liệu Xây dựng Hưng Thịnh", "Trang trại Bò sữa Ba Vì Xanh", "Cà phê Cao Nguyên Đỏ", "Mỹ phẩm Hoa Sen Trắng",
    "Điện máy Sài Gòn Mới", "Kho lạnh Mê Kông", "Chuỗi nhà thuốc Tâm An", "Trung tâm Ngoại ngữ Quốc Tế ABC",
    "Thời trang Mộc Lan", "Đồ gỗ Kim Sơn", "Sơn Phủ Cầu Vồng", "Pin Ắc quy Phương Nam Phát",
    "Giày da Đông Phong", "Gas Lửa Xanh Sài Thành", "Phim hoạt hình Cánh Diều", "Tổ chức Sự kiện Hoàn Cầu",
    "Kỹ thuật Điện Hưng Phát", "Thiết kế Nội thất Không Gian Xanh", "Thương mại Điện tử Chợ Lớn Online",
    "Đồ uống Hương Quê", "Chè Thái Nguyên Xanh", "Nông nghiệp Công nghệ cao Đà Lạt", "Bánh kẹo Hương Thu",
    "Hạt điều Bình Phước Vàng", "Xuất nhập khẩu Ánh Dương", "Môi trường Xanh Sạch", "Đầu tư Hạ tầng Thăng Long",
    "Cơ điện lạnh Toàn Cầu", "Bao bì Giấy Thuận An", "Dịch vụ Bảo vệ Long Hải", "Dịch vụ Vệ sinh Sạch Sẽ",
    "Phòng khám Nha khoa Nụ Cười", "Dịch vụ Hàng không Mây Trắng", "Đồ chơi Trẻ em Tuổi Thơ", "Văn phòng phẩm Hồng Lĩnh",
    "Bảo hiểm Nhân thọ Bình An", "Quỹ Tín dụng Nhân dân Phú Mỹ", "Chuỗi cà phê Góc Phố", "Viễn thông Kết Nối Việt",
    "Kiểm định Chất lượng Chuẩn Đo", "Công nghệ Sinh học Gene Việt", "Bất động sản Nghỉ dưỡng Vịnh Xanh",
    "Đào tạo Lái xe Thành Công", "Truyền hình Cáp Phương Đông", "Nội thất Văn phòng Hòa Bình", "Hệ thống Trường Liên cấp Ánh Sao",
    "Dịch vụ Tài chính Tiên Phong", "Quản lý Tòa nhà Landmark Mới", "Dệt nhuộm Nam Định Mới", "Nhựa Kỹ thuật Tiến Lực",
    "Thiết bị Điện Sao Vàng", "Phụ tùng Ô tô Việt Hàn", "Chế biến Gỗ Bình Dương Xanh", "Logistics Cửa Khẩu Lạng Sơn",
    "Sản xuất Bao bì Mềm Á Châu", "Thực phẩm Chay Tâm Đức", "Nước mắm Phan Thiết Xưa", "Hải sản Nha Trang Tươi",
    "Đầu tư Thương mại Hưng Gia", "Kinh doanh Than Quảng Ninh Mới", "Xăng dầu Miền Trung Phát", "Lắp máy Điện nước Hợp Lực",
    "Thiết bị Giáo dục Ánh Dương", "Phát triển Nhà Thủ Đức Mới", "Cơ khí Chính xác Việt Nhật", "Linh kiện Điện tử Bắc Ninh",
    "Dịch vụ Kế toán Tín Việt", "Công nghệ Thông tin Ánh Sáng", "Nông thủy sản An Giang Xanh", "Thiết bị Công nghiệp Hữu Nghị",
]
GOV_NAMES = [
    "Trường THPT Chuyên Nguyễn Huệ Mới", "Sở Giáo dục và Đào tạo (khối VP) - tỉnh Hòa An", "Trung tâm Y tế Quận Tây Hồ Mới",
    "Bệnh viện Đa khoa tỉnh Bình An", "Trường Đại học Kinh tế Hòa An (Phòng QTTB)", "Ban Quản lý Dự án Hạ tầng Đô thị Số 2",
    "Trường Cao đẳng Kỹ thuật Công nghệ Sài Gòn Mới", "Trường Tiểu học Ngôi Sao Xanh", "UBND Phường Phú Mỹ Mới (Văn phòng)",
    "Kho bạc Nhà nước khu vực Bình An (VP)", "Trung tâm Lưu trữ tỉnh Hòa An", "Thư viện tỉnh Bình An",
    "Trường THCS Lê Quý Đôn Mới", "Viện Nghiên cứu Nông nghiệp Phía Nam Mới", "Cục Thống kê tỉnh Hòa An (VP)",
    "Trung tâm Kiểm soát Bệnh tật tỉnh Bình An", "Trường Mầm non Hoa Sen Mới", "Đài Phát thanh Truyền hình tỉnh Hòa An",
    "Sở Tài nguyên và Môi trường tỉnh Bình An (VP)", "Trường Đại học Kỹ thuật Sông Hàn (Phòng CSVC)",
]
DEALER_NAMES = [
    "Cửa hàng Tin học Minh Khoa", "Đại lý VPP Thanh Hương", "Cửa hàng Máy tính Tuấn Phát", "Đại lý Mực in Hoàng Gia",
    "Cửa hàng Thiết bị Văn phòng Bảo An", "Đại lý Tin học Quang Trung", "Siêu thị Máy tính Phúc Lộc", "Đại lý VPP Kim Liên",
    "Cửa hàng Máy in Ngọc Lan", "Đại lý Thiết bị Mạng Sao Bắc", "Cửa hàng Linh kiện Hùng Cường", "Đại lý VPP Tân Bình Mới",
]

# Vendors: (code suffix, name, category, terms, branch)
VENDORS = [
    ("PP-DV", "Công ty TNHH Phân phối Tin học Đại Việt", "GOODS_IT", 45, "HN"),
    ("PP-TN", "Công ty CP Phân phối Thiết bị Thiên Nam", "GOODS_IT", 30, "HCM"),
    ("PP-SN", "Công ty TNHH Công nghệ Sao Nam Distribution", "GOODS_IT", 45, "HCM"),
    ("PP-HT", "Công ty CP Hạ tầng Mạng Hoàn Thiện", "GOODS_IT", 30, "HN"),
    ("PP-VP", "Công ty TNHH Thiết bị Văn phòng Việt Phú", "GOODS_OFF", 30, "HN"),
    ("PP-QT", "Công ty CP Máy văn phòng Quốc Thịnh", "GOODS_OFF", 45, "HCM"),
    ("PP-MI", "Công ty TNHH Mực in Kỹ thuật số Á Đông", "GOODS_CON", 30, "HN"),
    ("PP-GI", "Công ty CP Giấy và Văn phòng phẩm Bắc Sơn", "GOODS_CON", 15, "HN"),
    ("PP-GN", "Công ty TNHH Giấy Nam Việt", "GOODS_CON", 30, "HCM"),
    ("VC-NH", "Công ty CP Giao nhận Nhanh Hơn", "LOGISTICS", 30, "HN"),
    ("VC-BN", "Công ty TNHH Vận tải Bắc Nam Express Mới", "LOGISTICS", 30, "HCM"),
    ("MB-HN", "Công ty CP Đầu tư Tòa nhà Thành Công Tower", "RENT", 0, "HN"),
    ("MB-HCM", "Công ty TNHH Quản lý Bất động sản Sài Gòn Center", "RENT", 0, "HCM"),
    ("MB-DN", "Công ty CP Văn phòng cho thuê Sông Hàn", "RENT", 0, "DN"),
    ("DN-HN", "Công ty Điện lực khu vực Hà Nội Mới", "UTILITY", 10, "HN"),
    ("DN-HCM", "Công ty Điện lực khu vực Sài Gòn Mới", "UTILITY", 10, "HCM"),
    ("DN-DN", "Công ty Điện lực khu vực Đà Nẵng Mới", "UTILITY", 10, "DN"),
    ("VT-01", "Công ty Viễn thông Kết Nối Số", "TELECOM", 15, "HN"),
    ("MK-SM", "Công ty CP Truyền thông Sao Mai", "MARKETING", 30, "HN"),
    ("MK-DG", "Công ty TNHH Quảng cáo Số Digi Growth", "MARKETING", 15, "HCM"),
    ("PM-CL", "Công ty CP Phần mềm Đám Mây Xanh", "SOFTWARE", 30, "HN"),
    ("BH-AT", "Tổng Công ty Bảo hiểm An Tâm", "INSURANCE", 30, "HN"),
    ("VPP-HH", "Công ty TNHH Văn phòng phẩm Hồng Lĩnh Phát", "SUPPLIES", 30, "HN"),
    ("TK-NH", "Nhà hàng Hội An Quán", "ENTERTAIN", 0, "HN"),
    ("TK-SG", "Nhà hàng Sen Vàng Sài Gòn", "ENTERTAIN", 0, "HCM"),
    ("SC-OTO", "Garage Ô tô Thành Công Mới", "REPAIR", 15, "HN"),
    ("TB-OTO", "Công ty CP Ô tô Tải Đại Lộc", "ASSET", 0, "HN"),
    ("TB-NT", "Công ty TNHH Nội thất Văn phòng Hòa Thuận", "ASSET", 30, "HCM"),
    ("VT-DN", "Công ty TNHH Vật tư Kỹ thuật Miền Trung", "SUPPLIES", 30, "DN"),
    ("SK-HC", "Công ty TNHH Sự kiện Hoàn Cầu Mới", "MARKETING", 15, "HCM"),
]

LAST_NAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Phan", "Trịnh", "Đinh", "Lương", "Mai", "Tạ"]
MIDDLE_NAMES = ["Văn", "Thị", "Minh", "Đức", "Thu", "Ngọc", "Quang", "Thanh", "Hữu", "Hoài", "Gia", "Bảo", "Khánh", "Anh", "Hải", "Thùy", "Xuân", "Tuấn"]
FIRST_NAMES = ["An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hải", "Hạnh", "Hiếu", "Hoa", "Hùng", "Huyền", "Khánh", "Lan", "Linh", "Long",
               "Mai", "Minh", "Nam", "Nga", "Ngọc", "Nhung", "Phong", "Phúc", "Phương", "Quân", "Quỳnh", "Sơn", "Tâm", "Thảo", "Thắng",
               "Thủy", "Trang", "Trung", "Tú", "Tuấn", "Vân", "Việt", "Vy", "Yến", "Đạt", "Duy", "Hưng", "Kiên", "Loan", "Oanh"]

# Lunar New Year (Tết Nguyên đán) — business is closed and slow around these dates.
TET_DATES = {2025: date(2025, 1, 29), 2026: date(2026, 2, 17)}
PUBLIC_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 4, 30), date(2025, 5, 1), date(2025, 9, 1), date(2025, 9, 2), date(2025, 4, 7),
    date(2026, 1, 1), date(2026, 4, 30), date(2026, 5, 1), date(2026, 9, 1), date(2026, 9, 2), date(2026, 4, 27),
}
