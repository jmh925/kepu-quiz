@echo off
REM ============================================================
REM  科普闯关系统 · 一键启动并打开学生端网页版（Windows）
REM  需要先安装依赖：pip install -r backend\requirements.txt
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "PY=%KEPU_PYTHON%"
if "%PY%"=="" set "PY=python"

cd /d "%ROOT%\backend"
echo [kepu] 启动服务端 ...
echo [kepu] 学生端  http://127.0.0.1:8000/app/
echo [kepu] 管理端  http://127.0.0.1:8000/admin/
echo [kepu] 接口文档 http://127.0.0.1:8000/docs
echo.
start "" http://127.0.0.1:8000/app/
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
endlocal
