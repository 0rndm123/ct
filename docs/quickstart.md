# CT quick start: existing COT database and raw CFTC file downloads

The PostgreSQL database `"COT"` already exists, but has not been populated.

**Do not move the repository.** The paths are independent:

| Purpose | Windows path |
|---|---|
| Git source repository | `D:\OD\OneDrive\tech\GitHub\rndm123\ct` |
| Original CFTC files | `D:\OD\OneDrive\Fin\data\COT` |
| Database | PostgreSQL `"COT"` on `localhost:5432` |
| Schema | `cot` |

## 1. Pull the current repository

Use PowerShell in the existing Conda environment (e.g. `env_systrd`):

```powershell
cd "D:\OD\OneDrive\tech\GitHub\rndm123\ct"
git remote set-url origin git@github-rndm123:0rndm123/ct.git
git pull origin main
```

## 2. Start downloading original CFTC history now, independently of PostgreSQL

Only Python and `requests` are necessary to download files. No DB password is required:

```powershell
python -m pip install "requests>=2.32,<3"
.\scripts\download_history.bat --start-year 2025 --end-year 2025
```

The pilot downloads **all seven** official CFTC report datasets for calendar year 2025. You can instead start with one family:

```powershell
.\scripts\download_history.bat --start-year 2025 --end-year 2025 --datasets tff_futures
```

Then, download **all available years of all seven datasets**:

```powershell
.\scripts\download_history.bat
```

The full download is multi-year and makes many requests. It will reuse validated existing annual snapshots if interrupted and rerun.

Verify the stored raw files (no network/database):

```powershell
python -m cot_ingest.download verify
```

The downloader stores each exact official Socrata API JSON response body without rewriting it. It groups immutable snapshots as:

```text
D:\OD\OneDrive\Fin\data\COT\raw\cftc_api
  6dca-aqww
    history
      2025
        20261024T...-<unique>
          page_00000.json
          page_00001.json
          manifest.json
  jun7-fc8e
  72hh-3qpy
  kh3c-gbw2
  gpe5-46if
  yw9f-hn96
  4zgm-a668
```

File timestamps and names above are **illustrative**. The manifest records the CFTC dataset, source request URL, report date range, downloaded timestamp UTC, row count, page size, original file size and SHA-256. Each full, validated download is promoted from `.staging` into its final folder. Incomplete source downloads do not get promoted.

To capture a new immutable snapshot of a historical year that is already archived:

```powershell
.\scripts\download_history.bat --start-year 2025 --end-year 2025 --refresh
```

To download weekly snapshots after CFTC publishes the new report:

```powershell
.\scripts\download_weekly.bat
```

The weekly mode revisits the most recent 56 days of **position dates** and keeps new raw snapshots; source data may be revised or released late. A Saturday run is usually appropriate, but holidays require care.

## 3. Finish setting up the existing COT database

Install the PostgreSQL Python driver in the active environment:

```powershell
python -m pip install "psycopg[binary]>=3.2,<4"
.\scripts\setup_cot.bat
```

This Python script connects to existing `"COT"` on `localhost:5432` as admin (`postgres` by default). It interactively requests:
- PostgreSQL administrator password.
- New `cot_loader` password, twice.
- New `cot_app` password, twice.

It executes the SQL roles/grants and schema scripts, sets both separate passwords, and verifies application read-only rights. **Do not send or commit passwords.**

**SQL-only alternative:** In pgAdmin Query Tool, connected to the existing `"COT"` database as `postgres`, execute `sql/setup_existing_cot.sql`. It creates roles, all schema objects and grants but **does not set passwords**. To set passwords without putting them in SQL, use the Python setup tool.

Either way, no other database (`Trd`, etc.) is modified, and no existing `"COT"` database is dropped.

## 4. After setup, import archived files into PostgreSQL

Set secure connection access for `cot_loader` (e.g. Windows libpq `%APPDATA%\postgresql\pgpass.conf`) and a password-free-in-source DSN:

```powershell
$env:COT_DATABASE_URL = "postgresql://cot_loader@localhost:5432/COT"
.\scripts\load_history.bat --start-year 2025 --end-year 2025 --offline
.\scripts\verify.bat
```

The `--offline` option reads only validated source archives. The database ingester tracks the matching raw manifest for each window and does not contact CFTC to re-download that period.

For apps, use `cot_app` rather than the loader/admin credentials:
`postgresql://cot_app@localhost:5432/COT` (host/port adjusted if necessary).

## Testing and caveats

- The GitHub code is prepared, but **the scripts have not yet been run against your Windows PostgreSQL and OneDrive environment**.
- Do not confuse CFTC **Tuesday position date** with Friday release date when using COT in backtests.
- No original annual CFTC compressed ZIP files are downloaded. Here, “original files” means unaltered response bytes from the official CFTC Socrata API.
- The raw data and PostgreSQL must be reconciled before scheduling the full weekly end-to-end pipeline.
