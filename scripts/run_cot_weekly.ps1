<#
Recurring Windows COT update, intended for RUN_COT_WEEKLY.bat and Task Scheduler.
Must be run as the same Windows user who configured the DPAPI credential.
The target database and role are deliberately fixed.
#>
param(
    [ValidateRange(7,365)][int]$LookbackDays = 84
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$configDir = Join-Path $env:LOCALAPPDATA 'CT_COT'
$credentialFile = Join-Path $configDir 'cot_loader.dpapi'
$pythonFile = Join-Path $configDir 'python.path'
$logDir = Join-Path $configDir 'logs'
$null = New-Item -Path $logDir -ItemType Directory -Force
$log = Join-Path $logDir ('weekly_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
$transcriptOn = $false
$lock = $null
try {
    Start-Transcript -Path $log -ErrorAction Stop | Out-Null
    $transcriptOn = $true
    Write-Host ('COT weekly run started ' + (Get-Date -Format o))
    Write-Host ('Repository: ' + $repo)
    Write-Host ('Logging to: ' + $log)
    if (-not (Test-Path -LiteralPath $credentialFile)) {
        throw 'Missing protected cot_loader password. First run SETUP_COT_WEEKLY.bat interactively.'
    }
    if (-not (Test-Path -LiteralPath $pythonFile)) {
        throw 'Missing saved Python executable. Re-run SETUP_COT_WEEKLY.bat.'
    }
    $python = (Get-Content -LiteralPath $pythonFile -Raw -Encoding UTF8).Trim()
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw ('Configured Python executable does not exist: ' + $python)
    }

    # Local lock prevents two scheduled/manual runs of the same Windows user.
    # PostgreSQL additionally uses its own advisory lock during import.
    $lockFile = Join-Path $configDir 'weekly.lock'
    try {
        $lock = [System.IO.File]::Open($lockFile,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None)
    }
    catch [System.IO.IOException] {
        throw 'Another COT weekly run is already in progress.'
    }

    Push-Location $repo
    try {
        Write-Host ('Downloading and reconciling last ' + $LookbackDays + ' position-date days...')
        & $python -m cot_ingest.download weekly --lookback-days $LookbackDays
        if ($LASTEXITCODE -ne 0) {
            throw ('CFTC download failed with exit code ' + $LASTEXITCODE + '; database import skipped.')
        }

        Write-Host 'Configuring PostgreSQL cot_loader authentication...'
        $encrypted = (Get-Content -LiteralPath $credentialFile -Raw -Encoding UTF8).Trim()
        $secret = ConvertTo-SecureString -String $encrypted
        $credential = New-Object System.Management.Automation.PSCredential('cot_loader', $secret)
        $env:PGPASSWORD = $credential.GetNetworkCredential().Password
        $env:COT_DATABASE_URL = 'postgresql://cot_loader@localhost:5432/COT'
        $credential = $null
        $secret = $null

        Write-Host 'Importing all new/modified weekly files since 2019; unchanged SHA256 files are skipped...'
        # Include all locally available history to recover files missed by earlier DB runs.
        & $python -m cot_ingest.import_weekly --start-year 2019
        if ($LASTEXITCODE -ne 0) {
            throw ('COT database import failed with exit code ' + $LASTEXITCODE)
        }

        Write-Host 'Verifying COT PostgreSQL row counts and dataset coverage...'
        & $python -m cot_ingest.import_weekly --verify
        if ($LASTEXITCODE -ne 0) {
            throw ('COT database verification failed with exit code ' + $LASTEXITCODE)
        }

        Write-Host ('SUCCESS: COT weekly update finished ' + (Get-Date -Format o))
    }
    finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        Remove-Item Env:COT_DATABASE_URL -ErrorAction SilentlyContinue
        Pop-Location
    }
}
catch {
    Write-Host ('ERROR: COT weekly update FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    if ($null -ne $lock) { $lock.Dispose() }
    if ($transcriptOn) { Stop-Transcript | Out-Null }
}
