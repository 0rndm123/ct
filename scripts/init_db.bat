@echo off
setlocal
pushd "%~dp0.."
if not defined COT_ADMIN_USER set "COT_ADMIN_USER=postgres"
where psql >nul 2>nul
if errorlevel 1 (
    echo ERROR: psql not found on PATH. Add the PostgreSQL bin directory.
    popd
    exit /b 1
)
echo Creating COT database and roles cot_loader / cot_app...
psql -X -v ON_ERROR_STOP=1 -U "%COT_ADMIN_USER%" -d postgres -f "sql\00_create_database.sql"
if errorlevel 1 (
    echo ERROR: Database/role creation failed. Check PostgreSQL admin permissions.
    popd
    exit /b 1
)
echo Initializing schema as cot_loader using SET ROLE...
psql -X -v ON_ERROR_STOP=1 -U "%COT_ADMIN_USER%" -d COT -f "sql\01_schema.sql"
if errorlevel 1 (
    echo ERROR: Schema creation failed.
    popd
    exit /b 1
)
echo COT schema ready. If credentials were not configured, run scripts\set_passwords.bat
popd
exit /b 0
