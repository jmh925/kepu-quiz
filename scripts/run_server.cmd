@echo off
REM ============================================================
REM  科普知识闯关小程序 · 后端一键启动（Windows）
REM  用法：双击本文件，或在命令行执行 scripts\run_server.cmd
REM  说明：自动把仓库自带的依赖目录 backend\deps 加入模块搜索路径，
REM        因此无需 pip install 也能启动。
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"

if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"

cd /d "%BACKEND%"
echo [kepu] 启动服务端 http://127.0.0.1:8000
echo [kepu] 接口文档 http://127.0.0.1:8000/docs
echo [kepu] 管理端    http://127.0.0.1:8000/admin/
"%KEPU_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
endlocal
