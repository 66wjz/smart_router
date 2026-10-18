@echo off
cd /d "%~dp0"
echo ========================================
echo   Smart Router v5.2 - AI模型智能路由代理
echo ========================================
echo.
echo 管理后台与 API: http://localhost:10002
echo.

REM CH-029：指向 v5 入口（backend/run.py）。
REM 旧的 router.py 是 v4 遗留（无鉴权/无 SQLite），已不再使用。
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 backend\.venv，请先按 README 安装依赖。
    pause
    exit /b 1
)
set FRONTEND_DIST=%~dp0frontend\dist
".venv\Scripts\python.exe" run.py
pause
