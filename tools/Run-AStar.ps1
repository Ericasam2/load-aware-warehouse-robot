param(
    [ValidateSet('empty','raised_empty','loaded')][string]$Mode='empty',
    [string]$Start='RobotStart',
    [string]$Goal='Pickup_P1',
    [switch]$Verify,
    [string]$Python=''
)
$ErrorActionPreference='Stop'
if (!$Python) {
    $candidate=Get-Command python -ErrorAction SilentlyContinue
    if ($candidate) { $Python=$candidate.Source }
    else { $Python=Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' }
}
if (!(Test-Path -LiteralPath $Python)) { throw 'Specify -Python with an interpreter containing numpy and Pillow.' }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ($Verify) { & $Python -m warehouse_planning.planner --verify-suite }
    else { & $Python -m warehouse_planning.planner --mode $Mode "--start=$Start" "--goal=$Goal" }
    if ($LASTEXITCODE -ne 0) { throw 'Planning failed; inspect outputs/astar for the failure status.' }
} finally { Pop-Location }
