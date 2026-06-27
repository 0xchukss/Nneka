@echo off
setlocal
cd /d "%~dp0"

python -m pip install --upgrade --target "_vendor" imageio-ffmpeg
if errorlevel 1 (
  echo Setup failed.
  pause
  exit /b 1
)

python "%~dp0clip_shuffle.py" --help
pause
