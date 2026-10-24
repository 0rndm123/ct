@echo off
setlocal EnableExtensions
pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: Cannot access the CT repository directory.
    exit /b 1
)

REM One entry point for PowerShell: .\INSTALL_COT.bat
REM PostgreSQL "COT" must already exist; this never drops/creates databases.
REM Downloads and organizes 2019-present CFTC JSON, verifies, creates
REM the COT schema/roles, prompts for passwords and imports all local JSON.
REM To use only existing JSON (without connecting to the CFTC):
REM     .\INSTALL_COT.bat --existing
REM Requires Python 3.11+ and a PostgreSQL admin password.

set "PYEXE=python"
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"

if /I "%~1"=="--existing" (
    set "SKIP_DOWNLOAD=1"
) else if "%~1"=="" (
    set "SKIP_DOWNLOAD=0"
) else (
    echo ERROR: Unknown option "%~1".
    echo Usage: INSTALL_COT.bat [--existing]
    popd
    exit /b 2
)

echo.
echo ==== COT PostgreSQL setup and JSON import ====
echo Repository: %CD%
echo Source data: D:\OD\OneDrive\Fin\data\COT
echo Database: COT  ^(must already exist^)
echo.

"%PYEXE%" --version
if errorlevel 1 goto :no_python

echo Checking local SQL revision before downloading files or asking for passwords...
"%PYEXE%" scripts\check_schema.py
if errorlevel 1 goto :failed

echo [1/4] Checking required Python packages...
"%PYEXE%" -m pip install -r "requirements.txt"
if errorlevel 1 goto :failed

if "%SKIP_DOWNLOAD%"=="1" (
    echo [2/4] Using existing files only; no CFTC download...
) else (
    echo [2/4] Downloading CFTC history from 2019 to latest available year...
    "%PYEXE%" -m cot_ingest.download history --start-year 2019
    if errorlevel 1 goto :failed
)

echo [3/4] Verifying COT JSON files...
"%PYEXE%" -m cot_ingest.download verify --start-year 2019
if errorlevel 1 goto :failed

echo [4/4] Configuring COT PostgreSQL and loading JSON files...
echo You will be asked for the PostgreSQL admin password and to create
echo separate secure passwords for cot_loader and cot_app.
"%PYEXE%" "scripts\setup_and_load.py" --start-year 2019
if errorlevel 1 goto :failed

echo.
echo SUCCESS: COT schema and historical records imported.
echo You can inspect cot.v_report_coverage in pgAdmin ^(database COT^).
popd
exit /b 0

:no_python
echo ERROR: Python was not found. Activate your Python/Conda environment.
popd
exit /b 1

:failed
echo.
echo ERROR: Setup stopped. Read the first error above.
echo No database was dropped and existing source JSON files were not deleted.
popd
exit /b 1
