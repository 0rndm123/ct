@echo off
setlocal
pushd "%~dp0.."
where psql >nul 2>nul
if errorlevel 1 (
    echo ERROR: psql not found on PATH. Add the PostgreSQL bin directory.
    popd
    exit /b 1
)
echo Creating PostgreSQL database COT if it does not exist...
psql -X -v ON_ERROR_STOP=1 -d postgres -f "sql\00_create_database.sql"
if errorlevel 1 (
    echo ERROR: Could not create COT database. Check PGUSER, PGHOST and CREATEDB privileges.
    popd
    exit /b 1
)
echo Creating schema and loading source dataset registry...
psql -X -v ON_ERROR_STOP=1 -d COT -f "sql\01_schema.sql"
if errorlevel 1 (
    echo ERROR: COT schema initialization failed.
    popd
    exit /b 1
)
echo Schema ready.
popd
exit /b 0
