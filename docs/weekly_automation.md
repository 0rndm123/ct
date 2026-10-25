# Windows COT Weekly Task

## CFTC publication

The official CFTC COT release time is normally Friday **15:30 US Eastern**,
with Tuesday's position data. In Lisbon this is generally Friday 20:30, or
19:30 during some US/Europe daylight-saving transition weeks.

Official schedule:
https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm

User-requested task: **every Tuesday at 09:00**, Windows local clock.
The new Tuesday report is NOT available yet: it is typically made public
the following Friday. A Tuesday morning run collects the previous Friday's
publication; holidays can shift the official dates by 1-2 business days.

## Locations

Git source: D:\OD\OneDrive\tech\GitHub\rndm123\ct
JSON sources: D:\OD\OneDrive\Fin\data\COT\YYYY-MM-DD\report_type.json
Database: PostgreSQL COT / cot / cot_loader (read/write only)
Logs: %LOCALAPPDATA%\CT_COT\logs

## Install once

Prerequisite: the existing COT schema and initial history must have
already been loaded, e.g. with INSTALL_COT.bat --existing.

In PowerShell, with the Conda/Python environment that has psycopg/requests:

    cd "D:\OD\OneDrive\tech\GitHub\rndm123\ct"
    git remote set-url origin git@github-rndm123:0rndm123/ct.git
    git pull --ff-only origin main
    .\SETUP_COT_WEEKLY.bat

The setup asks once for the EXISTING cot_loader password, checks the DB login,
then saves a Windows DPAPI-encrypted password under the same user profile:

    %LOCALAPPDATA%\CT_COT\cot_loader.dpapi

The active Python executable is saved at:

    %LOCALAPPDATA%\CT_COT\python.path

The encrypted password is not committed to Git and no password is stored
in plaintext in the COT project or in the position-date JSON folders.
The same Windows profile must be used to run the scheduled task.
If Python or the password changes, rerun setup.

The setup registers the Task Scheduler entry:

    CT - COT Weekly Update

with a Tuesday 09:00 trigger in your Windows system's local timezone,
**only while the same Windows user is logged on**. The computer and local
PostgreSQL must be available. It is configured to start when available;
a missed run may start after login rather than exactly at 09:00.

## Execute a manual end-to-end test

    .\RUN_COT_WEEKLY.bat

No PostgreSQL password prompt. This performs:

1. Take a local lock to avoid concurrent jobs.
2. Download the CFTC reports for the most recent 84 days (all 7 datasets).
3. Store them under YYYY-MM-DD/reference-date JSON files. Equal content is
   NOT rewritten; updated CFTC data replaces the corresponding JSON atomically.
4. Import locally stored files from 2019 onward into PostgreSQL, skipping
   all unchanged file hashes registered in cot.source_files.
5. Validate the DB counts and report families.
6. Record stdout/stderr and execution results in a logfile under LocalAppData.

If download fails, PostgreSQL import is never started.
If a source file changed, only affected file content is imported.
If a contract disappears upstream, the importer refuses silent deletion.

The 84-day window can be changed manually:

    .\RUN_COT_WEEKLY.bat -LookbackDays 112

Old source gaps outside that period require a historical download;
the weekly routine does NOT re-download all years back to 2019.

## Inspect after execution

PowerShell:

    Get-ScheduledTask -TaskName 'CT - COT Weekly Update'

pgAdmin, inside PostgreSQL database COT:

    SELECT d.report_code, MAX(r.report_date) AS latest_date, COUNT(*) AS records
    FROM cot.reports r JOIN cot.datasets d USING(dataset_id)
    GROUP BY d.report_code ORDER BY d.report_code;

    SELECT run_id,mode,status,started_at,finished_at,error_message
    FROM cot.ingest_runs ORDER BY run_id DESC LIMIT 10;

This GitHub change does not itself install the Windows task. The setup BAT
must be run on the actual computer.
