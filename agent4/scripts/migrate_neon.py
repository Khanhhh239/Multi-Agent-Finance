"""Apply additive Neon migrations or print a secret-free dry-run plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "database" / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))


def migration_plan() -> list[dict[str, object]]:
    plan = []
    for path in migration_files():
        content = path.read_bytes()
        plan.append(
            {
                "version": path.name.split("_", 1)[0],
                "name": path.name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return plan


def apply_migrations(database_url: str) -> None:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on deployment extra
        raise RuntimeError(
            "Applying Neon migrations requires psycopg[binary,pool]; use --dry-run without it."
        ) from exc

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS cloud")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cloud.schema_migrations (
                version text PRIMARY KEY,
                checksum_sha256 char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        for item in migration_plan():
            version = str(item["version"])
            checksum = str(item["sha256"])
            cursor.execute(
                "SELECT checksum_sha256 FROM cloud.schema_migrations WHERE version = %s",
                (version,),
            )
            row = cursor.fetchone()
            if row:
                if row[0] != checksum:
                    raise RuntimeError(
                        f"migration checksum mismatch for {version}; use a forward fix"
                    )
                continue
            sql = (MIGRATIONS / str(item["name"])).read_text(encoding="utf-8")
            cursor.execute(sql)
            cursor.execute(
                """
                INSERT INTO cloud.schema_migrations (version, checksum_sha256)
                VALUES (%s, %s)
                """,
                (version, checksum),
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print migration metadata only")
    args = parser.parse_args(argv)
    plan = migration_plan()
    if args.dry_run:
        print(json.dumps({"migrations": plan}, ensure_ascii=True, indent=2))
        return 0
    database_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL or NEON_DATABASE_URL is required unless --dry-run is used")
    apply_migrations(database_url)
    print(json.dumps({"status": "applied", "versions": [item["version"] for item in plan]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
