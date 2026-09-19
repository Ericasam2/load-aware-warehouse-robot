param(
    [switch]$PrepareOnly,
    [string]$Container = 'ros2-jazzy-unity',
    [string]$Docker = "$env:LOCALAPPDATA/Programs/DockerDesktop/resources/bin/docker.exe"
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (!$PrepareOnly) {
    New-Item -ItemType Directory -Force -Path (Join-Path $repo 'outputs/ros_unity') | Out-Null
    '{"status":"PREPARING","passed":false}' | Set-Content -LiteralPath (Join-Path $repo 'outputs/ros_unity/run_report.json') -Encoding UTF8
}
if (!(Test-Path -LiteralPath $Docker)) { throw "Docker executable not found: $Docker" }
function Invoke-Docker {
    & $Docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($args -join ' ')" }
}
# Use the existing ROS container. Never replace or recreate it.
$geometry = Get-Content -LiteralPath (Join-Path $repo 'maps/scene_geometry.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$metadata = Get-Content -LiteralPath (Join-Path $repo 'maps/generated/metadata.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$sceneHash = (Get-FileHash -LiteralPath (Join-Path $repo ('unity_project/' + $geometry.scene_path)) -Algorithm SHA256).Hash.ToLowerInvariant()
$configHash = (Get-FileHash -LiteralPath (Join-Path $repo 'config/planning.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sceneHash -ne $geometry.scene_sha256) {
    throw 'Scene changed. Exit Unity Play, save WarehouseEnvironment, select Warehouse Robotics > Export A Star Planning Geometry, then run .\tools\Build-PlanningMap.ps1 -RunTests and retry.'
}
if ($sceneHash -ne $metadata.source_scene_sha256 -or $configHash -ne $metadata.config_sha256) {
    throw 'Generated maps are outdated. Run .\tools\Build-PlanningMap.ps1 -RunTests and retry.'
}
Invoke-Docker info --format '{{.ServerVersion}}'
Invoke-Docker start $Container
Invoke-Docker exec $Container mkdir -p /tmp/warehouse-astar/unity_project/Assets/Scenes
# Pass file paths rather than nested shell/Python strings: Windows PowerShell
# 5.1 strips embedded quotes when forwarding native executable arguments.
Invoke-Docker cp (Join-Path $PSScriptRoot 'ros_unity_runtime') "${Container}:/tmp/warehouse-astar/"
Invoke-Docker exec $Container bash /tmp/warehouse-astar/ros_unity_runtime/check_dependencies.sh
foreach ($folder in @('warehouse_planning','config','maps')) {
    Invoke-Docker cp (Join-Path $repo $folder) "${Container}:/tmp/warehouse-astar/"
}
Invoke-Docker cp (Join-Path $repo 'unity_project/Assets/Scenes/WarehouseEnvironment.unity') "${Container}:/tmp/warehouse-astar/unity_project/Assets/Scenes/"
# A listening endpoint is reused; starting two would compete for port 10000.
& $Docker exec $Container python3 /tmp/warehouse-astar/ros_unity_runtime/check_listener.py
if ($LASTEXITCODE -ne 0) {
    Invoke-Docker exec -d $Container bash /tmp/warehouse-astar/ros_unity_runtime/start_endpoint.sh
    $ready = $false
    for ($i=0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        & $Docker exec $Container python3 /tmp/warehouse-astar/ros_unity_runtime/check_listener.py
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
    }
    if (!$ready) { throw 'ROS endpoint failed. Inspect /tmp/warehouse-endpoint.log in the container.' }
}
if ($PrepareOnly) {
    Write-Host 'ROS endpoint ready. Open WarehouseEnvironment in Unity and press Play, then run this script without -PrepareOnly.'
    return
}
Write-Host 'Open WarehouseEnvironment and press Play at its saved start pose. Running empty RobotStart -> Pickup_P1.'
Push-Location $repo
try {
    & $Docker exec $Container bash /tmp/warehouse-astar/ros_unity_runtime/run_test.sh
    $runExit = $LASTEXITCODE
} finally {
    New-Item -ItemType Directory -Force -Path (Join-Path $repo 'outputs/ros_unity') | Out-Null
    & $Docker cp "${Container}:/tmp/warehouse-astar/outputs/ros_unity/." (Join-Path $repo 'outputs/ros_unity')
    Pop-Location
}
if ($runExit -ne 0) { throw 'Joint test did not pass. Inspect outputs/ros_unity/run_report.json.' }
Write-Host 'PASS: See outputs/ros_unity/run_report.json and actual_trajectory.csv.'
