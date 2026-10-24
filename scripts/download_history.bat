@echo off
setlocal
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python virtual environment missing. Run: py -3 -m venv .venv
  popd
  exit /b 1
)
REM CFTC originals are archived in D:\OD\OneDrive\Fin\data\COT.
REM This script never connects to PostgreSQL.
".venv\Scripts\python.exe" -m cot_ingest.download history %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
