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

## Position-date files since 2019

**[Date-first COT storage, historic download, import and migration guide](docs/date_based_storage.md)**

Keep Git source at `D:\OD\OneDrive\tech\GitHub\rndm123\ct`.
Original CFTC report records are saved to `D:\OD\OneDrive\Fin\data\COT\YYYY-MM-DD\<report>.json`.

One date folder corresponds to the **CFTC report reference/position date** (usually Tuesday),
never the download date. There are up to seven meaningful report-type JSON filenames in that folder.
Raw JSON record fields are preserved, with one array per report family and position date.

Use the following from an activated Python environment in the Git repo:

```powershell
git pull origin main
python -m pip install "requests>=2.32,<3"
.\scripts\organize_existing.bat
.\scripts\download_history.bat
.\scripts\verify_files.bat
```

Default complete history downloads **2019 through the current year**, for all seven CFTC datasets.
The existing legacy raw archive is not removed; use the organiser to reuse it, then move it
outside COT only after checking coverage. Current weekly source refresh: `scripts\download_weekly.bat`.

For independent database setup in existing PostgreSQL `"COT"`, run `scripts\setup_cot.bat`
after installing psycopg and authenticating as PostgreSQL administrator. Then, with
`COT_DATABASE_URL` set for `cot_loader`, run `scripts\import_history.bat`.
Weekly end-to-end download then import: `scripts\update_weekly.bat`.
Applications should use read-only `cot_app` credentials.

## Data model

- `cot.datasets`: source catalog; seven CFTC datasets.
- `cot.reports`: one row per contract market, dataset, and CFTC **position date** (usually Tuesday). Contains full original `payload JSONB`, source hash, searchable identifiers, open interest, and ingestion timestamps.
- `cot.report_revisions`: audit log when an API payload changes.
- `cot.ingest_runs`, `cot.ingest_windows`: execution tracking and source-vs-processed row count checks, with a source-file path for each ingestion window.
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
