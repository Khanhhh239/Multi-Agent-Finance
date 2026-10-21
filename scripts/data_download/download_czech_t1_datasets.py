"""Download the two official Czech invoice sources, with resumable health pages.

Python standard library only. Raw data and consolidated request metadata stay
under data/T1/raw/ (gitignored). Run the separate audit script after download.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
MF_URL = "https://data.mf.gov.cz/exports/faktury/faktury.csv"
HEALTH_URL = "https://faktury.mzcr.cz/rest/invoices"


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def verified_cache(target, metadata):
    """Size alone cannot establish identity when resuming a raw snapshot."""
    if not target.exists() or not metadata:
        return False
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    if target.stat().st_size != metadata["bytes"] or digest.hexdigest() != metadata["sha256"]:
        raise ValueError(f"Cached raw hash/size mismatch: {target}; preserve it and use a new --snapshot")
    return True


def get(url, target, max_bytes, json_response=False):
    for attempt in range(4):
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "FinanceProject-Research/1.0",
                "Accept": "application/json" if json_response else "*/*",
            })
            started = now()
            with urllib.request.urlopen(req, timeout=90) as response:
                expected = response.headers.get("Content-Length")
                if expected and int(expected) > max_bytes:
                    raise ValueError("Response exceeds download size bound")
                digest, count = hashlib.sha256(), 0
                with tmp.open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > max_bytes:
                            raise ValueError("Response exceeds download size bound")
                        digest.update(chunk)
                        stream.write(chunk)
                if expected and count != int(expected):
                    raise ValueError("Incomplete HTTP response")
                metadata = {
                    "url": url, "final_url": response.url, "started_at_utc": started,
                    "finished_at_utc": now(), "status": response.status,
                    "bytes": count, "sha256": digest.hexdigest(),
                    "headers": {k: v for k, v in response.headers.items() if
                                k.lower().startswith("x-pagination") or k.lower() in
                                ("content-type", "content-length", "last-modified", "etag")},
                }
            if json_response:
                rows = json.loads(tmp.read_bytes())
                if not isinstance(rows, list):
                    raise ValueError("Expected a JSON array")
                metadata["rows"] = len(rows)
                if rows and "id_invoice" in rows[0]:
                    ids = [r["id_invoice"] for r in rows]
                    metadata.update(invoice_id_min=min(ids), invoice_id_max=max(ids))
            if target.exists():
                verified_cache(target, metadata)
                tmp.unlink()
            else:
                tmp.replace(target)
            return metadata
        except ValueError:
            # A schema/size/snapshot conflict is not a transient HTTP failure.
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("Use between one and four workers")
    stamp = datetime.strptime(args.snapshot, "%Y-%m-%d").date().isoformat()
    base = ROOT / "data/T1/raw/czech" / stamp
    mf, health = base / "finance", base / "health"
    pages = health / "pages"
    for path in (mf, health, pages):
        path.mkdir(parents=True, exist_ok=True)
    manifest_path = base / "download_manifest.json"
    cached = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    cached_pages = {entry["page"]: entry for entry in cached.get("sources", {}).get("health", {}).get("pages", [])}
    manifest = {"schema_version": 2, "started_at_utc": now(), "snapshot": stamp, "sources": {}}
    metadata_requests = {}

    # Start both independent sources together, without overloading either server.
    def download_mf():
        target = mf / "faktury.csv"
        meta = cached.get("sources", {}).get("finance")
        if verified_cache(target, meta):
            print("Finance CSV already downloaded; SHA256 verified.", flush=True)
            return meta
        print("Downloading complete Finance CSV...", flush=True)
        meta = get(MF_URL, target, 1_000_000_000)
        print(f"Finance CSV complete: {meta['bytes']:,} bytes.", flush=True)
        return meta

    with ThreadPoolExecutor(max_workers=1) as finance_executor:
        mf_future = finance_executor.submit(download_mf)
        for endpoint in ("organizations", "imports"):
            metadata_requests[endpoint] = get(f"https://faktury.mzcr.cz/rest/{endpoint}?per-page=1000",
                health / f"{endpoint}_before.json", 15_000_000, True)
        first_url = HEALTH_URL + "?" + urllib.parse.urlencode({"per-page": 1000, "page": 1})
        first = get(first_url, pages / "page_0001.json", 20_000_000, True)
        headers = {k.lower(): v for k, v in first["headers"].items()}
        total, page_count = int(headers["x-pagination-total-count"]), int(headers["x-pagination-page-count"])
        if page_count > 2000:
            raise ValueError("Unexpected page count; check endpoint")
        print(f"Health source: {total:,} records, {page_count} pages.", flush=True)
        results = {1: first}
        errors = {}

        def page_job(page):
            target = pages / f"page_{page:04d}.json"
            meta = cached_pages.get(page)
            if verified_cache(target, meta):
                page_headers = {k.lower(): v for k, v in meta["headers"].items()}
                if int(page_headers.get("x-pagination-total-count", -1)) == total:
                    return page, meta
            url = HEALTH_URL + "?" + urllib.parse.urlencode({"per-page": 1000, "page": page})
            return page, get(url, target, 20_000_000, True)

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(page_job, n): n for n in range(2, page_count + 1)}
            for future in as_completed(futures):
                page = futures[future]
                try:
                    _, metadata = future.result()
                    results[page] = metadata
                except Exception as exc:
                    errors[page] = str(exc)
                if (len(results) + len(errors)) % 10 == 0 or len(results) + len(errors) == page_count:
                    print(f"Health pages complete: {len(results)}/{page_count}; errors: {len(errors)}.", flush=True)
        manifest["sources"]["finance"] = mf_future.result()
        manifest["sources"]["health"] = {
            "endpoint": HEALTH_URL, "expected_records": total, "expected_pages": page_count,
            "metadata_requests": metadata_requests,
            "downloaded_pages": len(results), "downloaded_records": sum(m["rows"] for m in results.values()),
            "page_errors": errors, "pages": [{"page": n, **results[n]} for n in sorted(results)],
        }
        save_json(manifest_path, manifest)

    verification_requests = {}
    redundant_checks = []
    for endpoint in ("organizations", "imports"):
        before = health / f"{endpoint}_before.json"
        after = health / f"{endpoint}_after.json"
        meta = get(f"https://faktury.mzcr.cz/rest/{endpoint}?per-page=1000", after, 15_000_000, True)
        unchanged = before.read_bytes() == after.read_bytes()
        verification_requests[endpoint] = {**meta, "payload_retained": not unchanged}
        manifest["sources"]["health"][endpoint + "_unchanged_during_download"] = unchanged
        if unchanged:
            redundant_checks.append(after)
    check = get(first_url, health / "first_page_after.json", 20_000_000, True)
    unchanged = check["sha256"] == first["sha256"]
    verification_requests["first_page"] = {**check, "payload_retained": not unchanged}
    manifest["sources"]["health"]["first_page_unchanged_during_download"] = unchanged
    manifest["sources"]["health"]["verification_requests"] = verification_requests
    if unchanged:
        redundant_checks.append(health / "first_page_after.json")
    manifest["finished_at_utc"] = now()
    manifest["complete"] = not errors and len(results) == page_count and sum(m["rows"] for m in results.values()) == total
    save_json(manifest_path, manifest)
    # Request hashes/timestamps are now saved; identical check bodies add no data.
    for path in redundant_checks:
        path.unlink()
    print(json.dumps({"manifest": str(manifest_path.relative_to(ROOT)), "complete": manifest["complete"],
                      "finance_bytes": manifest["sources"]["finance"]["bytes"],
                      "health_records": manifest["sources"]["health"]["downloaded_records"]}), flush=True)
    if not manifest["complete"]:
        raise SystemExit("Incomplete download; rerun to resume failed pages.")


if __name__ == "__main__":
    main()
