param([string]$Python = '', [switch]$RunTests)
$ErrorActionPreference = 'Stop'
if (!$Python) {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate) { $Python = $candidate.Source }
    else { $Python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' }
}
if (!(Test-Path -LiteralPath $Python)) { throw 'Pass -Python with a Python interpreter containing numpy and Pillow.' }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & $Python -m warehouse_planning
    if ($LASTEXITCODE -ne 0) { throw 'Map build failed. Check scene export freshness and validation output.' }
    if ($RunTests) {
        & $Python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Planning tests failed.' }
    }
} finally { Pop-Location }
