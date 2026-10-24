# COT by position/report date (one folder per week)

OneDrive data root: D:\OD\OneDrive\Fin\data\COT
Git repository remains: D:\OD\OneDrive\tech\GitHub\rndm123\ct

The data folder is flat except for the report-date folders:

    COT/
      2019-01-01/
        legacy_futures.json
        legacy_combined.json
        disaggregated_futures.json
        disaggregated_combined.json
        tff_futures.json
        tff_combined.json
        supplemental_cit.json
      2019-01-08/
        ...
      2026-10-20/
        ...

Dates are CFTC **position dates**, normally Tuesdays, not download or publication dates.
Each JSON array includes every CFTC market/contract record for that date from the
report family. Missing/empty report families do not create empty files.

## Download 2019 through present (seven CFTC datasets)

Run from the Git repository root in PowerShell:

    git pull origin main
    python -m pip install "requests>=2.32,<3"
    .\scripts\organize_existing.bat
    .\scripts\download_history.bat
    .\scripts\verify_files.bat

The organiser reuses previously downloaded old API JSON archives, if present.
The history command downloads every year 2019 through the current calendar year.
To run a small test first:

    .\scripts\download_history.bat --start-year 2019 --end-year 2019

Weekly update:

    .\scripts\download_weekly.bat

Repeated downloads do not modify identical files; corrected records replace the
corresponding JSON file atomically. Downloading does not require a PostgreSQL
connection, account, or password.

The original source field names and values are preserved, but weekly JSON files
are reconstructed by date from API response pages, not byte-for-byte original
HTTP response files. Those earlier original-byte API archives are preserved
separately by the non-destructive migration step.

## Import into COT PostgreSQL

Apply sql/01_schema.sql to COT with administrator access and the existing roles
(provides source_file tracking), configure COT_DATABASE_URL for cot_loader, then:

    .\scripts\import_history.bat
    .\scripts\import_weekly.bat

Scheduled end-to-end weekly operation:

    .\scripts\update_weekly.bat

The importer reads date-folders only. It checks row counts per dataset/date
and never silently deletes records.

## Removing the old clutter safely

Older downloads are still under:

    D:\OD\OneDrive\Fin\data\COT\raw

After verifying complete historical coverage, you can manually MOVE that
legacy raw folder to another backup location OUTSIDE COT. Do not delete it
without separately deciding whether byte-perfect API provenance is needed.
The new scripts never create dataset-ID directories under the COT root.

## Caution

A date folder represents the CFTC reference date, typically Tuesday. It is
not proof the information was already public that day. Backtests must use
a verified publication-availability date to avoid look-ahead bias.
