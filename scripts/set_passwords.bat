@echo off
setlocal
pushd "%~dp0.."
if not defined COT_ADMIN_USER set "COT_ADMIN_USER=postgres"
where psql >nul 2>nul
if errorlevel 1 (
    echo ERROR: psql not found on PATH.
    popd
    exit /b 1
)
echo.
echo Configure the cot_loader password. Input is handled securely by psql.
echo Do not enter the password in PowerShell commands or store it in GitHub.
psql -X -v ON_ERROR_STOP=1 -U "%COT_ADMIN_USER%" -d postgres -c "\password cot_loader"
if errorlevel 1 (
    echo ERROR: Unable to configure cot_loader password.
    popd
    exit /b 1
)
echo.
echo Configure the read-only cot_app password.
psql -X -v ON_ERROR_STOP=1 -U "%COT_ADMIN_USER%" -d postgres -c "\password cot_app"
if errorlevel 1 (
    echo ERROR: Unable to configure cot_app password.
    popd
    exit /b 1
)
echo Both passwords have been set. Keep a secure copy in a password manager.
popd
exit /b 0
