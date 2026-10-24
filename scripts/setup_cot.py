"""Securely finalize an already existing PostgreSQL database named exactly "COT".

Performs SQL role grants and schema installation and asks interactively for
cot_loader/cot_app passwords. No passwords are stored in source code or Git.

From the repository root:
  .\\.venv\\Scripts\\python.exe scripts\\setup_cot.py
"""
from __future__ import annotations

import argparse
from getpass import getpass
import os
from pathlib import Path
import sys

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
ROLE_SQL = ROOT / "sql" / "00_existing_database_roles.sql"
SCHEMA_SQL = ROOT / "sql" / "01_schema.sql"


def secret_for(role: str) -> str:
    while True:
        first = getpass(f"New password for {role} (minimum 14 characters): ")
        second = getpass(f"Confirm password for {role}: ")
        if first != second:
            print("Passwords do not match. Try again.")
            continue
        if len(first) < 14:
            print("Please use at least 14 characters.")
            continue
        return first


def bootstrap(
    host: str,
    port: int,
    admin_user: str,
    admin_password: str,
    loader_password: str,
    app_password: str,
) -> None:
    if loader_password == app_password:
        raise ValueError("Loader and application passwords must be different")
    if len(loader_password) < 14 or len(app_password) < 14:
        raise ValueError("Use passwords of at least 14 characters")
    if not ROLE_SQL.is_file() or not SCHEMA_SQL.is_file():
        raise FileNotFoundError("SQL setup files are missing from the repository")

    # This script NEVER creates or drops a database. COT must exist already.
    with psycopg.connect(
        host=host,
        port=port,
        dbname="COT",
        user=admin_user,
        password=admin_password,
        autocommit=True,
        connect_timeout=15,
    ) as conn:
        actual = conn.execute("SELECT current_database()").fetchone()[0]
        if actual != "COT":
            raise RuntimeError(f"Refusing changes in database {actual!r}")

        print("Configuring existing PostgreSQL roles in database COT...")
        with conn.transaction():
            conn.execute(ROLE_SQL.read_text(encoding="utf-8"))

        print("Creating/updating the cot schema, tables and read-only privileges...")
        # 01_schema.sql explicitly contains BEGIN/COMMIT and SET LOCAL ROLE cot_loader.
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))

        # Fixed, non-user-controllable role identifiers. SQL-quoted password literals
        # preserve any special characters. They are never printed or written to disk.
        for role, password in (
            ("cot_loader", loader_password),
            ("cot_app", app_password),
        ):
            statement = sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
            conn.execute(statement)

        rows = conn.execute(
            """SELECT n.nspname, c.relname, c.relkind
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'cot' AND c.relkind IN ('r','v')
               ORDER BY c.relname"""
        ).fetchall()
        writable_app = conn.execute(
            """SELECT
                has_schema_privilege('cot_app', 'cot', 'CREATE'),
                has_table_privilege('cot_app', 'cot.reports', 'INSERT'),
                has_table_privilege('cot_app', 'cot.reports', 'UPDATE'),
                has_table_privilege('cot_app', 'cot.reports', 'DELETE'),
                has_table_privilege('cot_app', 'cot.reports', 'SELECT'),
                has_table_privilege('cot_loader', 'cot.reports', 'INSERT')"""
        ).fetchone()
        if writable_app != (False, False, False, False, True, True):
            raise RuntimeError(
                "Unexpected PostgreSQL grants: review the permission matrix before using apps. "
                f"Observed privileges: {writable_app!r}"
            )
        expected = {"datasets", "reports", "report_revisions", "ingest_runs", "ingest_windows"}
        present = {name for _, name, kind in rows if kind == "r"}
        if not expected.issubset(present):
            raise RuntimeError(f"Missing required COT tables: {sorted(expected - present)}")

        print("\nCOT schema objects:")
        for schema, name, kind in rows:
            print(f"  {schema}.{name} ({'view' if kind == 'v' else 'table'})")
        print("\nSuccess: COT configured; cot_loader can write, cot_app can only read.")
        print("Credentials were not saved by this setup script.")
        print("Next: configure pgpass securely and run the separate CFTC downloader.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure roles/passwords/schema in an EXISTING PostgreSQL COT database."
    )
    parser.add_argument("--host", default=os.getenv("PGHOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PGPORT", "5432")))
    parser.add_argument("--admin-user", default=os.getenv("COT_ADMIN_USER", "postgres"))
    args = parser.parse_args(argv)
    try:
        print("Target PostgreSQL:", f"{args.host}:{args.port}/COT")
        print("Administrative role:", args.admin_user)
        admin_secret = getpass(f"Password for PostgreSQL administrator {args.admin_user}: ")
        loader_secret = secret_for("cot_loader")
        app_secret = secret_for("cot_app")
        bootstrap(args.host, args.port, args.admin_user,
                  admin_secret, loader_secret, app_secret)
        return 0
    except (psycopg.Error, ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
        print(f"ERROR: COT setup did not complete: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
