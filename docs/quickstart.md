# CT quick start: COT in one folder per reference date

## Locations

Code repository: D:\OD\OneDrive\tech\GitHub\rndm123\ct
Data folder: D:\OD\OneDrive\Fin\data\COT
PostgreSQL database: "COT" (already created manually)

The user-visible file structure is:

    COT\
      2019-01-01\
        legacy_futures.json
        legacy_combined.json
        disaggregated_futures.json
        disaggregated_combined.json
        tff_futures.json
        tff_combined.json
        supplemental_cit.json
      2019-01-08\
        ...
      2026-10-20\
        ...

Dates refer to CFTC **position dates**, not download dates. The examples above
only illustrate folder naming. CFTC history can contain reporting exceptions.

## Pull code (PowerShell)

    cd "D:\OD\OneDrive\tech\GitHub\rndm123\ct"
    git remote set-url origin git@github-rndm123:0rndm123/ct.git
    git pull origin main

## Download from 2019, independently of PostgreSQL

    python -m pip install "requests>=2.32,<3"
    .\scripts\organize_existing.bat
    .\scripts\download_history.bat
    .\scripts\verify_files.bat

Organise reuses legacy archives without removing the old originals. The historic
download covers all seven CFTC datasets for 2019 through the present. A pilot is:

    .\scripts\download_history.bat --start-year 2019 --end-year 2019

Weekly download of the latest eight weeks:

    .\scripts\download_weekly.bat

Source fields are preserved in per-date JSON arrays. Files are overwritten only
if the upstream contents changed. No DB connection is used for download.

To remove old visual clutter, once complete coverage is verified, manually
move the old raw hierarchy OUTSIDE the COT folder as a backup. The scripts do
not delete prior API bytes without permission.

## Set up the already existing PostgreSQL database

    python -m pip install "psycopg[binary]>=3.2,<4"
    .\scripts\setup_cot.bat

This asks interactively for the PostgreSQL admin password and separate
cot_loader/cot_app passwords, creates or verifies schema/tables and grants.
Never commit passwords. For a SQL-only alternative, use
sql/setup_existing_cot.sql in pgAdmin as administrator, but this does not
choose passwords.

Configure COT_DATABASE_URL for cot_loader securely, using OS/libpq secret
storage, then import from local weekly JSON files:

    .\scripts\import_history.bat
    .\scripts\import_weekly.bat

The weekly end-to-end BAT downloads from CFTC and then imports into COT:

    .\scripts\update_weekly.bat

Apps connect with cot_app for read-only SELECT access, not cot_loader.

## Caveats

- No code has been executed against your Windows/OneDrive installation here.
- The PostgreSQL schema must be updated to include the source_file column;
  setup_cot.bat or sql/01_schema.sql applies this change.
- Existing API raw-response archives and the new date-oriented JSON are not
  byte-identical; the new files retain the source records without changing
  fields or values. Original response bytes are kept in the legacy archive.
- Always distinguish the CFTC Tuesday position date from the date the report
  became publicly available when testing trading strategies.
