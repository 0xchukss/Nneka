@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=Nneka"
set "SCRIPT=%~dp0start_server.bat"

schtasks /Create /TN "%TASK_NAME%" /TR "\"%SCRIPT%\"" /SC ONLOGON /RL LIMITED /F
if errorlevel 1 (
  echo.
  echo Could not create the auto-start task.
  pause
  exit /b 1
)

echo.
echo Auto-start installed.
echo Nneka will start when you sign in to Windows.
echo URL: http://127.0.0.1:8765
pause
