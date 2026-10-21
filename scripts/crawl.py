#!/usr/bin/env python3
"""Tầng 1 + tầng 2 (Phần 5): crawl dữ liệu công khai cho Agent 1, có MANIFEST + SHA-256.

Chỉ tự động hoá nguồn công khai, không cần đăng nhập, giấy phép cho phép tải.
Nguồn cần đăng nhập / chấp nhận điều khoản (Kaggle Home Credit, M5, Freddie Mac,
Payment Times Úc) được in ở mục MANUAL, không tự động.

  python scripts/crawl.py --list
  python scripts/crawl.py --only wdi_vn,oxcgrt,uk_ppr,online_retail_ii,berka,customer_invoices
  python scripts/crawl.py --only sba_7a          # ~436 MB
  python scripts/crawl.py --only bpi2019         # ~729 MB, có kiểm MD5
"""
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "MANIFEST.json"
UA = "Mozilla/5.0 (Agent1-research-crawler/1.0; academic, non-commercial)"

SBA = "https://data.sba.gov/sites/default/files/uploaded_resources/"
BERKA = "https://raw.githubusercontent.com/jlacko/berka-dataset/HEAD/"

SOURCES = {
    "vn_listed_fy2024": dict(files=[
        ("https://smc.vn/wp-content/uploads/2025/05/BCTC-HOP-NHAT-SAU-KIEM-TOAN-2024-ENG.pdf", "vn_listed/SMC_FY2024_consolidated_EN.pdf"),
        ("https://smc.vn/wp-content/uploads/2025/04/CBTT-DINH-CHINH-BCTC-2024.pdf", "vn_listed/SMC_FY2024_correction.pdf"),
        ("https://www.thanhcong.com.vn/wp-content/uploads/2025/04/TCM_Thiet-ke_2024-CBTT-8.4.2025.pdf", "vn_listed/TCM_FY2024_annual_report.pdf")],
        license="Public issuer disclosures; copyright retained by issuers; no redistribution licence asserted",
        role="Independent descriptive DSO/DPO spot-check, one listed issuer per sector, not SME estimates or generator calibration"),
    "vn_bmp_fy2024": dict(files=[
        ("https://binhminhplastic.com.vn/Data/Sites/1/media/co-dong/bctn/20250415-bmp-ar-2024-vn-%28final%29.pdf", "vn_listed/BMP_FY2024_annual_report.pdf")],
        license="Public issuer disclosure; copyright retained; automated download returned HTTP403 on 2026-10-20",
        role="Independent plastics-sector DSO spot-check; incomplete until original report can be read"),
    "vn_tcm_fy2022": dict(files=[
        ("https://www.thanhcong.com.vn/wp-content/uploads/2023/03/20230324-TCM-BCTC-hop-nhat-nam-2022-da-kiem-toan_VN.pdf", "vn_listed/TCM_FY2022_consolidated.pdf")],
        license="Public issuer disclosure; copyright retained; no redistribution licence asserted",
        role="Independent textiles DSO/DPO spot-check from audited 2022 report; not a 2024 sector estimate"),
    "vn_ntp_fy2024": dict(files=[
        ("https://admin.nhuatienphong.vn/img/posts/1_f2284364f5cd0dd5e057ecb4e3e165f0BCTN%202024.pdf", "vn_listed/NTP_FY2024_annual_report.pdf")],
        license="Public issuer disclosure; copyright retained; no redistribution licence asserted",
        role="Independent plastics DSO/DPO spot-check from audited statements in 2024 annual report; not SME estimate"),
    # --- tầng 2: thống kê thật để hiệu chỉnh / kiểm định máy phát ---
    "uk_ppr": dict(files=[("https://check-payment-practices.service.gov.uk/export/csv/", "uk_ppr/payment_practices.csv")],
                   license="Open Government Licence v3.0", role="T12 hình dạng trễ 30/31-60/60+, tỷ lệ tranh chấp (T3)"),
    "oxcgrt": dict(files=[("https://raw.githubusercontent.com/OxCGRT/covid-policy-dataset/main/data/OxCGRT_compact_national_v1.csv",
                           "oxcgrt/OxCGRT_compact_national_v1.csv")],
                   license="CC BY 4.0", role="T7 mốc gãy cấu trúc Việt Nam 2020-2022; T12 chèn sốc"),
    # --- tầng 1: dữ liệu thật tương tự để chứng minh phương pháp ---
    "online_retail_ii": dict(files=[("https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
                                     "online_retail_ii/online_retail_ii.zip")],
                             license="CC BY 4.0", role="T4 doanh thu mới (mùa vụ, khách bán buôn), T1 nhịp mua của khách"),
    "berka": dict(files=[(BERKA + f, "berka/" + f) for f in
                         ("account.asc", "client.asc", "disp.asc", "district.asc", "loan.asc", "order.asc", "trans.asc")],
                  license="PKDD'99 public challenge data (mirror github.com/jlacko/berka-dataset)",
                  role="T6 độ phủ khoảng trên chuỗi dòng tiền thật; T7 điểm gãy; T2 vỡ nợ khoản vay"),
    "sba_7a": dict(files=[(SBA + "7a_504_foia_data_dictionary.xlsx", "sba/7a_504_foia_data_dictionary.xlsx"),
                          (SBA + "FOIA_7a_FY2010_FY2019_asof_260630.csv", "sba/FOIA_7a_FY2010_FY2019.csv"),
                          (SBA + "FOIA_7a_FY2020_Present_asof_260630.csv", "sba/FOIA_7a_FY2020_Present.csv")],
                   license="US Government public data (SBA FOIA)", role="T2 xác suất vỡ nợ doanh nghiệp nhỏ (PIF vs CHGOFF)"),
    "bpi2019": dict(files=[("https://ndownloader.figshare.com/files/24072995", "bpi2019/BPI_Challenge_2019.xes")],
                    license="CC BY 4.0", md5="4eb909242351193a61e1c15b9c3cc814",
                    role="T1 thời gian thanh toán hoá đơn thật (phía phải trả), T9 bằng chứng ghi sổ theo lô"),
    "customer_invoices": dict(files=[("https://raw.githubusercontent.com/SkywalkerHub/Payment-Date-Prediction/main/Dataset.csv",
                                      "customer_invoices/Dataset.csv")],
                              license="không rõ (bản sao GitHub của Kaggle pradumn203)", local_fallback=
                              r"C:\Users\Admin\Downloads\invoice_prediction\data\dataset.csv",
                              role="T1 bộ AR giống ERP (độ tin cậy C) — chỉ để thử phương pháp"),
}

WDI = {
    "NY.GDP.MKTP.KD.ZG": "GDP growth (annual %)",
    "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
    "FR.INR.LEND": "Lending interest rate (%)",
    "PA.NUS.FCRF": "Official exchange rate (LCU per US$)",
    "FS.AST.PRVT.GD.ZS": "Domestic credit to private sector (% of GDP)",
    "NY.GDP.MKTP.CD": "GDP (current US$)",
}

MANUAL = [
    ("Home Credit installments_payments", "https://www.kaggle.com/competitions/home-credit-default-risk/data", "Kaggle login + chấp nhận luật cuộc thi"),
    ("M5 Forecasting", "https://www.kaggle.com/competitions/m5-forecasting-accuracy/data", "Kaggle login + luật cuộc thi"),
    ("Australia Payment Times Register", "https://register.paymenttimes.gov.au/data.html", "chấp nhận Terms of Use"),
    ("Freddie Mac SF Loan-Level", "https://freddiemac.com/research/datasets/sf-loanlevel-dataset", "đăng ký"),
    ("SEC Financial Statement Data Sets", "https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets",
     "bắt buộc User-Agent có tên tổ chức + email liên hệ của chính bạn; không tự điền"),
    ("UNU-WIDER Viet Nam SME", "https://www.wider.unu.edu/database/viet-nam-sme-database", "điền biểu mẫu"),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(path, algo="sha256"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print("  [skip] %s" % dest.relative_to(RAW))
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    pos = part.stat().st_size if part.exists() else 0
    h = {"User-Agent": UA}
    if pos:
        h["Range"] = "bytes=%d-" % pos
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=300) as r:
        mode = "ab" if pos and r.status == 206 else "wb"
        with open(part, mode) as f:
            shutil.copyfileobj(r, f, 1 << 20)
    part.replace(dest)
    print("  [ok] %s (%d bytes)" % (dest.relative_to(RAW), dest.stat().st_size))
    return dest


def fetch_wdi():
    out = RAW / "wdi_vn" / "wdi_vietnam.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = ["indicator,name,year,value"]
    for code, name in WDI.items():
        url = "https://api.worldbank.org/v2/country/VNM/indicator/%s?format=json&per_page=20000" % code
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
            j = json.loads(r.read())
        for x in (j[1] or []) if isinstance(j, list) and len(j) > 1 else []:
            rows.append('%s,"%s",%s,%s' % (code, name, x["date"], "" if x["value"] is None else x["value"]))
    out.write_text("\n".join(rows), encoding="utf-8")
    print("  [ok] wdi_vn rows=%d" % (len(rows) - 1))
    return [out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    keys = list(SOURCES) + ["wdi_vn"]
    if a.list or not a.only:
        for k, s in SOURCES.items():
            print("%-18s %-40s %s" % (k, s["license"][:40], s["role"]))
        print("%-18s %-40s %s" % ("wdi_vn", "CC BY 4.0", "biến vĩ mô Việt Nam (T6 kịch bản, T12)"))
        print("\nMANUAL:")
        for n, u, how in MANUAL:
            print("  - %s | %s | %s" % (n, u, how))
        return
    want = [k.strip() for k in a.only.split(",") if k.strip()]
    if any(k not in keys for k in want):
        sys.exit("unknown keys: %s" % [k for k in want if k not in keys])
    man = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    failures=[]
    for k in want:
        print("[%s]" % k)
        try:
            if k == "wdi_vn":
                paths, spec = fetch_wdi(), dict(license="CC BY 4.0", role="macro")
            else:
                spec = SOURCES[k]
                paths = []
                for url, rel in spec["files"]:
                    try:
                        paths.append(fetch(url, RAW / rel))
                    except Exception as e:  # noqa: BLE001
                        fb = spec.get("local_fallback")
                        if not fb or not Path(fb).exists():
                            raise
                        print("  [fallback] %s -> copy local %s (%s)" % (rel, fb, e))
                        (RAW / rel).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(fb, RAW / rel)
                        paths.append(RAW / rel)
                if spec.get("md5"):
                    got = sha(paths[0], "md5")
                    if got != spec["md5"]:
                        raise RuntimeError("md5 mismatch %s" % got)
            man[k] = dict(license=spec["license"], role=spec["role"], fetched_utc=now(),
                          files=[dict(path=str(p.relative_to(RAW)).replace("\\", "/"), bytes=p.stat().st_size,
                                      sha256=sha(p)) for p in paths])
            MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print("  [fail] %s: %s" % (k, e))
            failures.append(k)
    if failures:
        raise SystemExit('Failed sources: '+','.join(failures))


if __name__ == "__main__":
    main()
