# PostgreSQL COT: setup and import

The PostgreSQL database "COT" already exists on localhost:5432.
The Git source repo remains D:\OD\OneDrive\tech\GitHub\rndm123\ct.
The date-based JSON files are under D:\OD\OneDrive\Fin\data\COT.

## First load: one Windows command

PowerShell in the existing CT repository:

    cd "D:\OD\OneDrive\tech\GitHub\rndm123\ct"
    git remote set-url origin git@github-rndm123:0rndm123/ct.git
    git pull origin main
    python -m pip install -r requirements.txt
    .\scripts\verify_files.bat
    .\scripts\setup_and_load.bat

The last command prompts for:
1. Existing PostgreSQL administrator password (user postgres by default).
2. New cot_loader password (enter and confirm).
3. Different cot_app password (enter and confirm).

It creates or updates the existing COT schema, tables, indexes, audit triggers,
views and grants, and imports all local JSON from 2019 onwards. No passwords
are saved in SQL, Git or new config files. Data loading connects as cot_loader
with credentials held only in process memory.

If JSON files have not yet been downloaded:

    .\scripts\download_history.bat --start-year 2019 --end-year 2026

The initial loader imports 2026 data **if the corresponding local JSON exists**.
CFTC positions are identified by their reference dates, not download dates.

## Setup only

    .\scripts\setup_and_load.bat --setup-only

Or execute sql/setup_existing_cot.sql in pgAdmin, connected to the existing COT
database as administrator. The SQL-only route does not set login passwords.

## Subsequent imports

When cot_loader authentication is configured using a secure local secret
facility, e.g. Windows libpq %APPDATA%\postgresql\pgpass.conf:

    $env:COT_DATABASE_URL = "postgresql://cot_loader@localhost:5432/COT"
    .\scripts\import_history.bat
    .\scripts\import_weekly.bat

Subsequent unchanged JSON files are skipped based on their SHA-256. Changed
source rows are upserted and prior values audited. Missing source contracts
cause a row-count mismatch and a rollback, not a silent deletion.

Once the weekly manual run succeeds, the full pipeline is:

    .\scripts\update_weekly.bat

## Inspect with pgAdmin

Select the COT database and execute:

    SELECT report_code, family, universe FROM cot.datasets ORDER BY 1;
    SELECT min(report_date), max(report_date), count(*) FROM cot.reports;
    SELECT report_date, report_code, contract_rows
    FROM cot.v_report_coverage ORDER BY report_date DESC, report_code LIMIT 30;
    SELECT dataset_id,report_date,commodity_name,open_interest
    FROM cot.reports ORDER BY report_date DESC LIMIT 20;
    SELECT report_code, report_date, cftc_contract_market_code, payload
    FROM cot.v_latest_reports LIMIT 10;

For detailed controls, open sql/02_quality_checks.sql.

## Data model

- cot.datasets: official CFTC report source catalog, seven datasets.
- cot.reports: indexed contract/report/date keys, plus complete source JSONB.
- cot.source_files: source filepath, SHA-256, row count, load timestamps.
- cot.report_revisions: previous report JSON when changed upstream.
- cot.ingest_runs and cot.ingest_windows: job and file-level import audit.
- cot.v_latest_reports, cot.v_numeric_metrics, cot.v_report_coverage: query views.

The database is not populated until the script runs on the local machine.
This implementation validates stored JSON and their transfer to PostgreSQL,
but it does not independently prove that every historical weekly CFTC
publication was downloaded. Verify full weekly coverage separately.
