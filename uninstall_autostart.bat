@echo off
setlocal

set "TASK_NAME=Nneka"
schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 (
  echo.
  echo Could not remove the auto-start task, or it was not installed.
  pause
  exit /b 1
)

echo.
echo Auto-start removed.
pause
