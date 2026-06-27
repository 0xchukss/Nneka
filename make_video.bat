@echo off
setlocal
cd /d "%~dp0"

if not exist "_vendor\imageio_ffmpeg" (
  echo Installing local FFmpeg helper. This only touches this tool folder.
  python -m pip install --upgrade --target "_vendor" imageio-ffmpeg
  if errorlevel 1 (
    echo.
    echo Setup failed. Install Python packages with internet enabled, or install FFmpeg manually.
    pause
    exit /b 1
  )
)

set "AUDIO_FILE="
for %%E in (mp3 wav m4a aac flac ogg) do (
  for %%F in ("%~dp0audio\*.%%E") do (
    if exist "%%~fF" if not defined AUDIO_FILE set "AUDIO_FILE=%%~fF"
  )
)

if defined AUDIO_FILE (
  python "%~dp0clip_shuffle.py" --input-dir "%~dp0input_videos" --audio "%AUDIO_FILE%" --clip-seconds 2.0
) else (
  python "%~dp0clip_shuffle.py" --input-dir "%~dp0input_videos" --clip-seconds 2.0
)

echo.
pause
