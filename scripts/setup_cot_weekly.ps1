<#
Interactive one-time setup for RUN_COT_WEEKLY.bat.
Stores cot_loader password under Windows DPAPI for CURRENT WINDOWS USER ONLY.
Sets a Tuesday 09:00 (PC local time) Task Scheduler job in interactive-user mode.
No plaintext password or admin credentials are stored in Git or OneDrive COT.
#>
param(
    [string]$TaskName = 'CT - COT Weekly Update'
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This task setup requires Windows.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $repo 'RUN_COT_WEEKLY.bat'
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw ('Missing weekly BAT launcher: ' + $runner)
}
$configDir = Join-Path $env:LOCALAPPDATA 'CT_COT'
$null = New-Item -Path $configDir -ItemType Directory -Force

$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $python = (Resolve-Path $venvPython).Path
} else {
    $command = Get-Command python -CommandType Application -ErrorAction Stop
    $python = $command.Source
}
Write-Host ('Python selected: ' + $python)
Write-Host 'Enter the EXISTING password of cot_loader (not the PostgreSQL admin password).'
$secure = Read-Host 'cot_loader password' -AsSecureString
if ($null -eq $secure -or $secure.Length -eq 0) {
    throw 'No password supplied.'
}
$credential = New-Object System.Management.Automation.PSCredential('cot_loader', $secure)
$env:PGPASSWORD = $credential.GetNetworkCredential().Password
$env:COT_DATABASE_URL = 'postgresql://cot_loader@localhost:5432/COT'
try {
    & $python -c 'import psycopg; c=psycopg.connect("postgresql://cot_loader@localhost:5432/COT",connect_timeout=15); assert c.execute("SELECT current_database()").fetchone()[0]=="COT"; c.execute("SELECT count(*) FROM cot.datasets"); c.execute("SELECT count(*) FROM cot.source_files"); c.close(); print("PostgreSQL COT login and schema OK")'
    if ($LASTEXITCODE -ne 0) {
        throw 'cot_loader login or COT schema validation failed. Run INSTALL_COT.bat --existing first.'
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:COT_DATABASE_URL -ErrorAction SilentlyContinue
}

# ConvertFrom-SecureString without a custom key uses Windows DPAPI scoped
# to the current user's Windows profile. Decryption requires that same user.
$credentialFile = Join-Path $configDir 'cot_loader.dpapi'
$secure | ConvertFrom-SecureString | Set-Content -LiteralPath $credentialFile -Encoding UTF8 -NoNewline
$python | Set-Content -LiteralPath (Join-Path $configDir 'python.path') -Encoding UTF8 -NoNewline
$credential = $null
$secure = $null

Write-Host ('Protected credential stored in your Windows profile: ' + $credentialFile)
Write-Host 'This user profile is required for unattended execution.'
$who = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At '09:00'
$action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\cmd.exe') -Argument ('/d /c ""' + $runner + '""') -WorkingDirectory $repo
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$principal = New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Limited
$null = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host ('Scheduled Windows task: ' + $TaskName)
Write-Host 'Every Tuesday at 09:00 (local Windows time).'
Write-Host ('User: ' + $who + ' (must be logged in for the task to run).')
Write-Host ('Weekly logs: ' + (Join-Path $configDir 'logs'))
Write-Host 'Run RUN_COT_WEEKLY.bat manually once to validate the whole pipeline.'
