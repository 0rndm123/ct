# Windows installation and raw data lifecycle

This repository has **two different OneDrive destinations**. Do not move the Git repository to the finance data directory.

| Purpose | Exact location |
| --- | --- |
| Git repository (code/SQL/BAT/tests/docs) | `D:\OD\OneDrive\tech\GitHub\rndm123\ct` |
| Original CFTC source files | `D:\OD\OneDrive\Fin\data\COT` |
| PostgreSQL database | `"COT"` (quoted uppercase) |
| PostgreSQL schema | `cot` |

## PostgreSQL security model

- `cot_loader` owns the database/schema and loads/updates source data.
- `cot_app` can only connect and read the database (schema USAGE + SELECT grants). This is the account recommended for **apps**, dashboards, SysTrd read-only adapters, and queries.
- The PostgreSQL administrator (usually `postgres`) is needed only for provisioning and schema maintenance.
- No password is committed to GitHub. Credentials are created through interactive `psql \password` prompts, and can be rotated later with the same script.
- Do **not** share the `cot_loader` password with applications that merely read data.

## 1. Clone / update code

```powershell
cd "D:\OD\OneDrive\tech\GitHub\rndm123\ct"
git pull origin main
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Initialize PostgreSQL and generate account passwords

PostgreSQL and its `psql.exe` CLI must be installed (add the PostgreSQL `bin` folder to your PATH).

```powershell
.\scripts\init_db.bat
.\scripts\set_passwords.bat
```

The first BAT provisions a database named `"COT"` (not `cot`), creates `cot_loader` and `cot_app`, and creates the schema and tables as `cot_loader`. It does not replace existing passwords.

The second BAT interactively asks you to **enter and confirm a password separately for each role**. PostgreSQL's `\password` command avoids placing passwords inside SQL files or shell arguments. Store them in a password manager.

If the admin role isn't `postgres`, before running these BATs set `$env:COT_ADMIN_USER = "YOUR_ADMIN_USER"`.

A local-only PostgreSQL instance is a sensible default. Do not expose TCP port 5432 to the internet without appropriate networking/authentication controls.

## 3. Configure authentication for unattended scripts

The `cot_ingest` Python client uses `COT_DATABASE_URL` (and normal libpq authentication). Recommended DSN **without an embedded password**:

```powershell
$env:COT_DATABASE_URL = "postgresql://cot_loader@localhost:5432/COT"
```

On Windows, the libpq password file is outside GitHub:

`%APPDATA%\postgresql\pgpass.conf`

Example contents (replace placeholders with the **actual** passwords entered securely above):

```text
localhost:5432:COT:cot_loader:LOADER_PASSWORD
localhost:5432:COT:cot_app:APP_PASSWORD
```

Protect this file with appropriate Windows ACLs. If passwords contain a colon or backslash, escape those characters according to libpq pgpass syntax. The scheduled task must run as the Windows user who owns this file and has `COT_DATABASE_URL` set (or provide a separate secure task configuration).

For consuming applications use a different connection string:

```text
postgresql://cot_app@localhost:5432/COT
```

The database and roles are prepared by the BATs, but passwords and `pgpass.conf` must be set on **your** Windows machine; the GitHub connector cannot configure local PostgreSQL.

## 4. Original source-file archive

Default base folder: `D:\OD\OneDrive\Fin\data\COT`.

Files automatically created by the loader:

```text
COT/
└── raw/
    └── cftc_api/
        ├── 6dca-aqww/
        │   ├── history/
        │   │   └── 2025/
        │   │       └── 20261024T200000Z-<unique-id>/
        │   │           ├── page_00000.json
        │   │           ├── page_00001.json
        │   │           └── manifest.json
        │   └── weekly/
        │       └── 20260829_20261025/
        │           └── 20261024T200000Z-<unique-id>/
        │               ├── page_00000.json
        │               └── manifest.json
        ├── jun7-fc8e/
        ├── 72hh-3qpy/
        ├── kh3c-gbw2/
        ├── gpe5-46if/
        ├── yw9f-hn96/
        ├── 4zgm-a668/
        └── .staging/
```

The above timestamps are **examples**, not files that have already been downloaded. File layout is created on the machine where the loader runs.

- Each `.json` page stores the **unaltered JSON response body** from the official CFTC API. Pagination is needed because a historical year can be larger than one API request.
- `manifest.json` records which dataset, exact date range, query, page URLs, original byte sizes, row counts, hashes (SHA-256), and UTC download timestamp.
- Downloads enter `.staging`, then only complete/verified snapshots are promoted into the permanent archive.
- PostgreSQL report rows are updated **only after every source page has been saved and checksum-validated**.
- The database tracks the exact archive `manifest.json` used for each import in `cot.ingest_windows.archive_manifest`.
- History downloads are cached and reused. Use `--refresh-archive` to capture a new immutable copy of a historical year.
- Weekly runs always capture a new immutable snapshot. Use `--offline` to replay existing snapshots for an identical date window (or historical years).
- No CSV, ZIP or JSON raw files are stored inside the Git repository.

To choose a different base folder deliberately, set `COT_RAW_DIR`. **Normally do not set it**, as the correct OneDrive default is already configured.

## 5. Validate and run

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\load_history.bat --start-year 2025 --end-year 2025
.\scripts\verify.bat
```

Check both the local raw-file archive and the database before loading older years.

```powershell
.\scripts\load_history.bat
.\scripts\update_weekly.bat
```

The first full-history execution starts from the earliest date available in each official dataset. The weekly process has a 56-day overlap and stores a new set of raw JSON files each time.

To reprocess previously downloaded years without accessing CFTC:

```powershell
.\scripts\load_history.bat --start-year 2025 --end-year 2025 --offline
```

To explicitly download historical revisions again:

```powershell
.\scripts\load_history.bat --start-year 2025 --end-year 2025 --refresh-archive
```

For reporting and checks:

```powershell
psql -U cot_app -d COT -c "SELECT report_code, count(*) FROM cot.v_latest_reports GROUP BY 1 ORDER BY 1"
psql -U cot_app -d COT -f sql\02_quality_checks.sql
```

## What is not yet done

- **No one has executed these scripts on the local Windows machine**. The database, users, passwords and source directories remain to be created locally.
- The official API and PostgreSQL connectivity require an integration test, starting with a 2025 pilot.
- Windows Task Scheduler registration is a separate step, after the first successful weekly manual execution.
- Official yearly CFTC ZIP files are not downloaded by this implementation. This project stores exact responses from the official Socrata API; ZIP-source reconciliation can be added separately.
