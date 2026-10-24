# Technical decisions / validation checklist

## Requirements
- Separate **PostgreSQL database `"COT"`**, not a schema in SysTrd/TRD. Schema `cot` lives only in that database.
- Official CFTC source of truth. Entire history, all seven report datasets, weekly refresh.
- Full raw columns retained in JSONB; no data loss from heterogeneous report formats.
- Safe reruns (UPSERT), detecting duplicates, unexpected row losses, source count mismatches and revisions.
- Batch launchers for Windows; credentials never hard-coded into BAT/SQL/GitHub.

## Source decision
- Primary: CFTC Public Reporting Environment, Socrata API `/resource/{dataset_id}.json`.
- Recovery/reconciliation: historical annual ZIP archives at cftc.gov; **archive loading is not implemented** in phase 1.
- No third-party data required; source has no compulsory token (CFTC asks users not to overload API).
- Dataset availability: Legacy Futures Only 1986; Legacy Combined 1995; Disaggregated/TFF from June 2006; Supplemental CIT from January 2006.
- Always treat `report_date` as **position date**, NOT publication date. Friday 15:30 ET is typical publication time, with documented exceptions. Store first ingestion timestamp but do not pretend it is original publication time.

## Design rationale
- PostgreSQL dataset registry; one common table with a composite business key and `payload JSONB`; audit of changed values. Raw numeric columns can be accessed via `cot.v_numeric_metrics`.
- `id` is stored but **not used as a primary key**, reflecting CFTC's statement that there is no primary key.
- Source API pagination uses ordered pages, bounded year windows for historical work and an overlap window for weekly.
- A yearly/windowed download must match CFTC source count; the DB must match its source total for the same window. Failure is explicit. No destructive automatic cleanup.
- Maintain a session-level advisory lock to prevent two ingesters operating simultaneously.
- All operations explicitly reject any PostgreSQL database other than `"COT"`.

## Initial rollout gates
1. Validate source metadata/API schema and accessibility with a single report year first.
2. Create `"COT"`; execute schema SQL, inspect seven registry rows.
3. Pilot `history --start-year 2025 --end-year 2025`, check all seven ingestion windows.
4. Rerun the same pilot; rows must remain constant; revisions should remain zero.
5. Load history for all families, review 1986/1992/1995/2006 data boundaries.
6. Schedule weekly process for Saturday in Portuguese local time. Rerun on holiday release delays (a 56-day overlap catches missed updates at the next run).
7. Before using COT in a trading backtest, separately implement a verified release-availability calendar or a conservative release lag; Tuesday positioning cannot be known on Tuesday.

## Explicitly deferred
- Cross-check against ZIP archive row counts and sample values (second source implementation).
- Stable canonical instrument mapping into SysTrd, especially when contracts are renamed, consolidated or delisted.
- Semantic long/short category views and COT Index derived series (family-specific field mappings require verification).
- Full column-level source metadata/snapshot diffs as upstream API schemas evolve.
- External notification/monitoring; current run and window tables already record failures.

## Sources
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- https://publicreporting.cftc.gov/stories/s/r4w3-av2u
- https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm
