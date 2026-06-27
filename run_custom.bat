@echo off
setlocal
cd /d "%~dp0"

if not exist "_vendor\imageio_ffmpeg" (
  python -m pip install --upgrade --target "_vendor" imageio-ffmpeg
  if errorlevel 1 exit /b 1
)

python "%~dp0clip_shuffle.py" %*
