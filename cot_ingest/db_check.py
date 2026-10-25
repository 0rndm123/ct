"""Verify that the scheduled loader can connect to database COT with read/write rights.

Uses COT_DATABASE_URL and PGPASSWORD from the current process environment.
Passwords are never emitted, stored or included in command-line arguments.
"""
from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    dsn = os.environ.get("COT_DATABASE_URL")
    if dsn != "postgresql://cot_loader@localhost:5432/COT":
        print("ERROR: Only the configured localhost COT/cot_loader DSN is allowed.",
              file=sys.stderr)
        return 1
    try:
        with psycopg.connect(dsn, connect_timeout=15) as conn:
            database, role = conn.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            if (database, role) != ("COT", "cot_loader"):
                raise RuntimeError(f"Unexpected PostgreSQL identity: {role} at {database}")
            for relation in ("cot.datasets", "cot.source_files", "cot.reports"):
                conn.execute(f"SELECT count(*) FROM {relation}").fetchone()
            print("COT PostgreSQL connection OK (cot_loader / localhost:5432 / COT)")
        return 0
    except (psycopg.Error, RuntimeError) as exc:
        print(f"COT PostgreSQL verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
