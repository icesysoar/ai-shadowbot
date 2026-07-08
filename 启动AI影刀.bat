@echo off
chcp 65001 >nul
set "PY=C:\Users\Soara\.workbuddy\binaries\python\envs\l5bridge\Scripts\python.exe"
set "RUN=E:\WorkBuddy\自动系统\ai_shadowbot\run_server.py"
if not exist "%PY%" (
  echo [X] 找不到 Python: %PY%
  echo     请确认 l5bridge 虚拟环境已安装。
  pause
  exit /b 1
)
if not exist "%RUN%" (
  echo [X] 找不到启动脚本: %RUN%
  pause
  exit /b 1
)
echo ============================================
echo   AI Shadow (AI 影刀) - 启动工作流画布
echo ============================================
echo.
echo 正在启动网关并打开画布...
"%PY%" "%RUN%"
echo.
echo 若画布未自动弹出，请手动访问: http://localhost:8792/
echo 关闭弹出的【网关】窗口即可停止服务。
pause
