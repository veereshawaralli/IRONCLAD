$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12+ from python.org, then reopen PowerShell.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 LTS, then reopen PowerShell.' }
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install it and retry.' }
}
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $python -m pip install -e '.[dev,production]'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location web
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
New-Item -ItemType Directory -Force '.ironclad' | Out-Null
if (Test-Path '.env') {
    foreach ($line in Get-Content '.env') {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=(.*)$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            if ($value) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
        }
    }
}
if (-not $env:IRONCLAD_ADMIN_TOKEN) {
    if (-not (Test-Path '.ironclad/admin-token')) {
        & $python -c "import secrets,pathlib; pathlib.Path('.ironclad/admin-token').write_text(secrets.token_urlsafe(32))"
    }
    $env:IRONCLAD_ADMIN_TOKEN = (Get-Content '.ironclad/admin-token' -Raw).Trim()
}
Write-Host 'IRONCLAD: http://localhost:8000' -ForegroundColor Green
Write-Host ('Local access token: ' + $env:IRONCLAD_ADMIN_TOKEN)
Write-Host 'Keep this terminal open. Press Ctrl+C to stop. Actual verification requires Docker.'
$worker = Start-Process -FilePath $python -ArgumentList '-m','ironclad.worker' -PassThru -NoNewWindow -RedirectStandardOutput '.ironclad/worker.log' -RedirectStandardError '.ironclad/worker-error.log'
try {
    & $python -m uvicorn ironclad.api:create_app --factory --host 127.0.0.1 --port 8000
} finally {
    if (-not $worker.HasExited) { Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue }
}
