# CH-022 演示环境启动脚本
# 用独立 demo.db 跑在 10198 端口，不影响 10002 的生产/日常环境
#
# 用法：
#   .\run_demo.ps1              # 启动（需先跑 seed_demo_ch022.py 生成演示库）
#   .\run_demo.ps1 -Reseed      # 重建演示数据后再启动

param(
    [switch]$Reseed
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$DemoDb = Join-Path $Backend "demo.db"

if (-not (Test-Path $Python)) {
    Write-Host "找不到虚拟环境: $Python" -ForegroundColor Red
    exit 1
}

if ($Reseed -or -not (Test-Path $DemoDb)) {
    Write-Host "生成演示数据..." -ForegroundColor Cyan
    & $Python (Join-Path $Root "test\seed_demo_ch022.py")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# 前端构建产物（若存在则由后端托管 SPA）
$Dist = Join-Path $Root "frontend\dist"
if (Test-Path $Dist) {
    $env:FRONTEND_DIST = $Dist
}

$env:SMART_ROUTER_DB = $DemoDb

Write-Host ""
Write-Host "演示环境启动中..." -ForegroundColor Green
Write-Host "  数据库: $DemoDb"
Write-Host "  地址:   http://127.0.0.1:10198"
Write-Host "  账号:   admin / smart-router-2026"
Write-Host ""

Set-Location $Backend
& $Python -c "import uvicorn; from app.main import app; uvicorn.run(app, host='127.0.0.1', port=10198)"
