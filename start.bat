@echo off
cd /d "%~dp0"
echo ========================================
echo   Smart Router - AI模型智能路由代理
echo ========================================
echo.
echo 代理地址: http://localhost:10002
echo 上游NewAPI: http://124.222.235.3:10001
echo.
echo 统一模型名: smart-latest / smart-chat / auto-chat
echo.

pip install fastapi uvicorn httpx pyyaml -q 2>nul

python router.py
pause
