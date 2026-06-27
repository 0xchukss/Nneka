@echo off
setlocal
cd /d "%~dp0"

if not exist "_vendor\flask" (
  echo Installing local web UI dependency. This only touches this tool folder.
  python -m pip install --upgrade --target "_vendor" flask
  if errorlevel 1 (
    echo.
    echo Could not install Flask. Check internet/Python and run this again.
    pause
    exit /b 1
  )
)

if not exist "_vendor\imageio_ffmpeg" (
  echo Installing local FFmpeg helper. This only touches this tool folder.
  python -m pip install --upgrade --target "_vendor" imageio-ffmpeg
  if errorlevel 1 (
    echo.
    echo Could not install FFmpeg helper. Check internet/Python and run this again.
    pause
    exit /b 1
  )
)

python "%~dp0server.py"
