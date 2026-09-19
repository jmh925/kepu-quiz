@echo off
REM ============================================================
REM  科普知识闯关小程序 · 后端接口冒烟测试（Windows）
REM  产物：backend\tests\smoke_report.md（论文第 6 章表 6-1～表 6-3 的实测数据）
REM  前置：先在另一个窗口运行 scripts\run_server.cmd
REM ============================================================
setlocal
set "ROOT=%~dp0.."
if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"
cd /d "%ROOT%\backend"
"%KEPU_PYTHON%" tests\smoke_test.py
endlocal
