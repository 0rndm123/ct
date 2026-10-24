# CT — CFTC Commitments of Traders

Independent Python/PostgreSQL ingestion project. Target PostgreSQL database: **COT** (separate from SysTrd/TRD).

## Official source

- [CFTC Public Reporting Environment](https://publicreporting.cftc.gov/stories/s/r4w3-av2u)
- [CFTC historic compressed annual archives](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm)
- [CFTC official release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm)

The primary data source is **the official CFTC Socrata API**, not a paid or third-party provider. Seven datasets are ingested without dropping source columns: the full API object is persisted in PostgreSQL JSONB, alongside searchable keys and common attributes. Individual report families have different columns, which should not be silently forced into one fixed wide table.

| Dataset | Socrata ID | Earliest nominal year |
| --- | --- | --- |
| Legacy Futures Only | `6dca-aqww` | 1986 |
| Legacy Futures & Options Combined | `jun7-fc8e` | 1995 |
| Disaggregated Futures Only | `72hh-3qpy` | 2006 |
| Disaggregated Combined | `kh3c-gbw2` | 2006 |
| TFF Futures Only | `gpe5-46if` | 2006 |
| TFF Combined | `yw9f-hn96` | 2006 |
| Supplemental CIT | `4zgm-a668` | 2006 |

CFTC documentation states that **no provided ID column is a guaranteed primary key**. The local key combines report dataset, position date, CFTC contract market code, and market/exchange name; any duplicate source keys within the same extraction window are rejected rather than silently discarded.

## Locations and installation

| Purpose | Location |
| --- | --- |
| Repository (source code) | `D:\OD\OneDrive\tech\GitHub\rndm123\ct` |
| Archived, original CFTC API files | `D:\OD\OneDrive\Fin\data\COT` |
| PostgreSQL database | `"COT"` |
| PostgreSQL schema | `cot` |

**Original files are saved and validated in OneDrive BEFORE updating PostgreSQL.** Each API response page is stored as an unmodified JSON file, together with a manifest containing source URL, exact query, SHA-256 hash, row count and UTC timestamp. Files are immutable and auditable. History is reused locally; new weekly snapshots are kept.

The local PostgreSQL setup provisions two separate accounts: `cot_loader` (schema owner, read/write ingestion) and `cot_app` (read-only applications). Passwords are chosen interactively on the Windows computer and are **never committed to this repo**.

For full details see **[Windows installation, passwords, raw file layout, and validation](docs/windows_setup.md)**.

Quick start from the repository root (requires local PostgreSQL, Python 3.11+, and `psql` on PATH):

```powershell
git pull origin main
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\init_db.bat
.\scripts\set_passwords.bat
```

Then set up libpq credential storage on the local machine (`%APPDATA%\postgresql\pgpass.conf`) and configure:

```powershell
$env:COT_DATABASE_URL = "postgresql://cot_loader@localhost:5432/COT"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\load_history.bat --start-year 2025 --end-year 2025
.\scripts\verify.bat
# Once the pilot is validated:
.\scripts\load_history.bat
.\scripts\update_weekly.bat
```

Advanced commands:

```powershell
.\.venv\Scripts\python.exe -m cot_ingest.cli list-datasets
.\scripts\load_history.bat --start-year 2025 --end-year 2025 --offline
.\scripts\load_history.bat --start-year 2025 --end-year 2025 --refresh-archive
```

Schedule the weekly BAT after the usual Friday release once the manual pipeline has been integration-tested. A 56-day position-date overlap captures delayed publications, with an immutable raw snapshot per execution.

## Data model

- `cot.datasets`: source catalog; seven CFTC datasets.
- `cot.reports`: one row per contract market, dataset, and CFTC **position date** (usually Tuesday). Contains full original `payload JSONB`, source hash, searchable identifiers, open interest, and ingestion timestamps.
- `cot.report_revisions`: audit log when an API payload changes.
- `cot.ingest_runs`, `cot.ingest_windows`: execution tracking and source-vs-processed row count checks, with a local original-file manifest path for each ingestion window.
- `cot.v_latest_reports`, `cot.v_numeric_metrics`: analytical views (the latter expands numeric raw fields dynamically, including currently unknown CFTC numeric columns).

## Data quality and interpretation

- **Position date is NOT publication date**. Usually Tuesday's positions are released Friday at 15:30 US Eastern. Backtests should not make Tuesday's COT data available to a strategy before Friday's release. Historical exact release timestamps are not available in all circumstances; do not invent them.
- US holidays can delay release; a Saturday job can be rerun without duplication. To recover delayed releases, rerun after the adjusted release date, or schedule a secondary weekday retry.
- Futures Only and Futures + Options Combined are **alternative report universes**; do not sum them. Option positions are generally delta-adjusted.
- Historical data includes contract launches, retirements, category changes and classification methodology limitations; no assumption of a stable instrument universe.
- The CFTC covers **reportable US-regulated futures markets**, not all worldwide asset positions or spot cryptocurrency exchange flows.
- The official legacy Futures Only history is available from 1986 but pre-September-1992 records are not weekly. The historical disaggregated and TFF series backfill to June 2006, subject to the CFTC's retrospective classification limitations.
- The official annual ZIP files are a future reconciliation/fallback path; API JSON response files are the original files archived in this implementation, not annual ZIP downloads.

## Suggested validation gates

1. Pilot with one recent year across seven datasets.
2. Compare source count and rows fetched for each dataset/year.
3. Validate distinct business keys, null identifiers and extreme/negative positions.
4. Run the same period twice and verify that counts and payloads do not change.
5. Inspect the seven datasets' raw numeric schemas before adding semantic indicators or linking to SysTrd.

No automatic deletion takes place when a record disappears upstream: a discrepancy must be reviewed explicitly.
