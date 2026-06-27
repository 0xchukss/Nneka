# Nneka

Fast local editor for making shuffled music-video timelines from videos you own or are licensed to reuse.

## Fastest Use

1. Put source videos in `input_videos`.
2. Put your song/audio file in `audio`.
3. Double-click `make_video.bat`.
4. The finished MP4 appears in your Windows `Downloads` folder.

By default every shot is cut to exactly `2.000` seconds, source clip audio is removed, and your own audio is added if the `audio` folder contains a file.

## Browser UI

Double-click `start_server.bat`, then open:

```text
http://127.0.0.1:8765
```

The web UI lets you upload source videos and audio, set clip length with values like `2.00s`, create a horizontal, vertical, or square export, and watch render progress.

## Auto-Start On Windows

To avoid starting the server manually every time, double-click `install_autostart.bat` once.

To remove auto-start later, double-click `uninstall_autostart.bat`.

## Custom Command

```bat
run_custom.bat --input-dir "C:\path\to\videos" --audio "C:\path\to\song.mp3" --clip-seconds 2.0
```

Useful options:

- `--clip-seconds 2.0` sets the precise shot length.
- `--width 1080 --height 1920` makes a vertical Shorts/TikTok style video.
- `--seed 123` repeats the same shuffle.
- `--output "C:\Users\Hp\Downloads\my_video.mp4"` chooses a specific output name.
- `--keep-work` keeps the rendered 2-second clips for inspection.

This tool does not download videos from YouTube. Use only footage you own, have licensed, or are legally allowed to reuse.
