#!/usr/bin/env python3
"""
Nneka

Builds a shuffled music video from video files you own or are licensed to use.
Default behavior:
  - cuts source videos into exact 2.000 second silent clips
  - shuffles clips while avoiding original neighbor order where possible
  - adds your own audio when provided
  - exports the final MP4 to the Windows Downloads folder
"""

from __future__ import annotations

import argparse
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "_vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


@dataclass(frozen=True)
class Segment:
    source_path: Path
    source_index: int
    segment_index: int
    start: float


def run_command(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    kwargs = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    return subprocess.run(args, **kwargs)


def find_ffmpeg() -> str:
    env_path = os.environ.get("FFMPEG_EXE")
    if env_path and Path(env_path).exists():
        return env_path

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise SystemExit(
            "FFmpeg was not found.\n"
            "Run setup.bat once, or install FFmpeg and add it to PATH.\n"
            f"Details: {exc}"
        )


def media_duration(ffmpeg: str, path: Path) -> float:
    result = run_command([ffmpeg, "-hide_banner", "-i", str(path)], capture=True)
    text = f"{result.stderr}\n{result.stdout}"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        raise RuntimeError(f"Could not read duration for {path}")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def discover_videos(input_dir: Path, explicit_videos: list[Path]) -> list[Path]:
    videos = [p.resolve() for p in explicit_videos]
    if input_dir.exists():
        for path in sorted(input_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(path.resolve())

    seen = set()
    unique = []
    for path in videos:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def build_segments(ffmpeg: str, videos: list[Path], clip_seconds: float) -> list[Segment]:
    segments: list[Segment] = []
    for source_index, path in enumerate(videos):
        duration = media_duration(ffmpeg, path)
        full_segments = int(math.floor((duration + 0.0001) / clip_seconds))
        if full_segments <= 0:
            print(f"Skipping too-short video: {path.name}")
            continue
        for segment_index in range(full_segments):
            segments.append(
                Segment(
                    source_path=path,
                    source_index=source_index,
                    segment_index=segment_index,
                    start=segment_index * clip_seconds,
                )
            )
    return segments


def has_original_neighbor_pair(ordered: list[Segment]) -> bool:
    for left, right in zip(ordered, ordered[1:]):
        if is_original_neighbor_pair(left, right):
            return True
    return False


def is_original_neighbor_pair(left: Segment, right: Segment) -> bool:
    if left.source_index != right.source_index:
        return False
    return abs(left.segment_index - right.segment_index) == 1


def shuffle_segments(
    segments: list[Segment],
    *,
    needed_count: int | None,
    seed: int | None,
    avoid_original_neighbors: bool,
) -> list[Segment]:
    rng = random.Random(seed)
    if needed_count is None:
        needed_count = len(segments)

    output: list[Segment] = []
    while len(output) < needed_count:
        deck = list(segments)
        best = None
        for _ in range(400):
            rng.shuffle(deck)
            candidate = list(deck)
            has_bad_bridge = (
                bool(output)
                and bool(candidate)
                and is_original_neighbor_pair(output[-1], candidate[0])
            )
            if (
                not avoid_original_neighbors
                or (not has_original_neighbor_pair(candidate) and not has_bad_bridge)
            ):
                best = candidate
                break
            best = candidate
        output.extend(best or deck)

    return output[:needed_count]


def default_output_path() -> Path:
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return downloads / f"nneka_{stamp}.mp4"


def render_clip(
    ffmpeg: str,
    segment: Segment,
    clip_path: Path,
    *,
    clip_seconds: float,
    width: int,
    height: int,
    fps: int,
    crf: int,
) -> None:
    vf = (
        f"fps={fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"trim=duration={clip_seconds:.6f},"
        "setpts=PTS-STARTPTS,"
        "setsar=1"
    )
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-accurate_seek",
        "-ss",
        f"{segment.start:.6f}",
        "-i",
        str(segment.source_path),
        "-t",
        f"{clip_seconds:.6f}",
        "-an",
        "-vf",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        str(clip_path),
    ]
    result = run_command(cmd, capture=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to render clip from {segment.source_path.name}: {result.stderr}")


def write_concat_file(paths: list[Path], concat_file: Path) -> None:
    lines = []
    for path in paths:
        safe = str(path).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    concat_file.write_text("\n".join(lines), encoding="utf-8")


def concat_video(ffmpeg: str, clip_paths: list[Path], video_path: Path) -> None:
    concat_file = video_path.with_suffix(".txt")
    write_concat_file(clip_paths, concat_file)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(video_path),
    ]
    result = run_command(cmd, capture=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to concatenate clips: {result.stderr}")


def mux_audio(
    ffmpeg: str,
    video_path: Path,
    audio_path: Path | None,
    output_path: Path,
    *,
    duration: float | None,
) -> None:
    if audio_path:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
        ]
        if duration:
            cmd.extend(["-t", f"{duration:.6f}"])
        cmd.extend(["-movflags", "+faststart", str(output_path)])
    else:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    result = run_command(cmd, capture=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create final video: {result.stderr}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut legal/owned source videos into exact 2-second shuffled clips and export an MP4."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "input_videos",
        help="Folder containing source videos. Default: input_videos beside this script.",
    )
    parser.add_argument("--video", action="append", type=Path, default=[], help="Add a specific source video file.")
    parser.add_argument("--audio", type=Path, help="Your own song/audio file to place under the shuffled video.")
    parser.add_argument("--output", type=Path, default=default_output_path(), help="Output MP4 path.")
    parser.add_argument("--clip-seconds", type=float, default=2.0, help="Clip length in seconds. Default: 2.0.")
    parser.add_argument("--seed", type=int, help="Use a fixed shuffle seed for repeatable results.")
    parser.add_argument("--width", type=int, default=1920, help="Output width. Default: 1920.")
    parser.add_argument("--height", type=int, default=1080, help="Output height. Default: 1080.")
    parser.add_argument("--fps", type=int, default=30, help="Output frame rate. Default: 30.")
    parser.add_argument("--crf", type=int, default=20, help="Video quality: lower is better/larger. Default: 20.")
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep temporary clips for inspection instead of deleting them.",
    )
    parser.add_argument(
        "--allow-original-neighbors",
        action="store_true",
        help="Allow clips that were neighbors in the original source to sit next to each other.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.clip_seconds <= 0:
        raise SystemExit("--clip-seconds must be greater than 0.")

    ffmpeg = find_ffmpeg()
    videos = discover_videos(args.input_dir, args.video)
    if not videos:
        raise SystemExit(
            "No source videos found.\n"
            f"Put MP4/MOV/etc files in: {args.input_dir}\n"
            "Only use videos you own or have permission/license to reuse."
        )

    audio_path = args.audio.resolve() if args.audio else None
    if audio_path and not audio_path.exists():
        raise SystemExit(f"Audio file not found: {audio_path}")

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Reading source durations...")
    segments = build_segments(ffmpeg, videos, args.clip_seconds)
    if not segments:
        raise SystemExit(f"No full {args.clip_seconds:.3f}s clips could be made from the source videos.")

    audio_duration = media_duration(ffmpeg, audio_path) if audio_path else None
    needed_count = math.ceil(audio_duration / args.clip_seconds) if audio_duration else None
    ordered = shuffle_segments(
        segments,
        needed_count=needed_count,
        seed=args.seed,
        avoid_original_neighbors=not args.allow_original_neighbors,
    )

    print(f"Source videos: {len(videos)}")
    print(f"Available exact clips: {len(segments)}")
    print(f"Clips in final timeline: {len(ordered)}")
    print(f"Clip length: {args.clip_seconds:.3f}s")
    if audio_duration:
        print(f"Audio duration: {audio_duration:.3f}s")

    temp_root = Path(tempfile.mkdtemp(prefix="nneka_"))
    try:
        clip_paths = []
        for index, segment in enumerate(ordered, start=1):
            clip_path = temp_root / f"clip_{index:05d}.mp4"
            print(f"[{index}/{len(ordered)}] {segment.source_path.name} @ {segment.start:.3f}s")
            render_clip(
                ffmpeg,
                segment,
                clip_path,
                clip_seconds=args.clip_seconds,
                width=args.width,
                height=args.height,
                fps=args.fps,
                crf=args.crf,
            )
            clip_paths.append(clip_path)

        silent_video = temp_root / "silent_timeline.mp4"
        concat_video(ffmpeg, clip_paths, silent_video)
        mux_audio(ffmpeg, silent_video, audio_path, output_path, duration=audio_duration)

        print("")
        print(f"Done: {output_path}")
        return 0
    finally:
        if args.keep_work:
            print(f"Kept working files: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
