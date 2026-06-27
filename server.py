#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "_vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))
IS_VERCEL = bool(os.environ.get("VERCEL"))
RUNTIME_DIR = Path(os.environ.get("TMPDIR") or "/tmp") / "nneka" if IS_VERCEL else ROOT

try:
    from flask import Flask, jsonify, redirect, render_template_string, request, send_file, url_for
except Exception as exc:
    raise SystemExit(
        "Flask is not installed for the web UI.\n"
        "Run: python -m pip install --upgrade --target \"_vendor\" flask\n"
        f"Details: {exc}"
    )


JOBS_DIR = RUNTIME_DIR / "server_jobs"
DOWNLOADS = RUNTIME_DIR / "downloads" if IS_VERCEL else Path.home() / "Downloads"
ALLOWED_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024 * 1024
JOBS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS.mkdir(parents=True, exist_ok=True)


@dataclass
class Job:
    id: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    log: list[str] = field(default_factory=list)
    output_path: str | None = None
    error: str | None = None


jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()


def add_log(job_id: str, line: str) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job.log.append(line.rstrip())
        job.log = job.log[-300:]


def set_job(job_id: str, **updates: object) -> None:
    with jobs_lock:
        job = jobs[job_id]
        for key, value in updates.items():
            setattr(job, key, value)


def safe_filename(name: str, fallback: str) -> str:
    keep = []
    for char in name:
        if char.isalnum() or char in "._- ":
            keep.append(char)
        else:
            keep.append("_")
    cleaned = "".join(keep).strip(" .")
    return cleaned or fallback


def save_uploads(files, target_dir: Path, allowed: set[str], fallback_prefix: str) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, file_storage in enumerate(files, start=1):
        if not file_storage or not file_storage.filename:
            continue
        filename = safe_filename(file_storage.filename, f"{fallback_prefix}_{index}")
        suffix = Path(filename).suffix.lower()
        if suffix not in allowed:
            continue
        destination = target_dir / filename
        file_storage.save(destination)
        saved.append(destination)
    return saved


def run_job(job_id: str, video_dir: Path, audio_path: Path | None, args: dict[str, object]) -> None:
    set_job(job_id, status="running")
    add_log(job_id, "Starting exact 2.000 second clip shuffle...")

    orientation = str(args.get("orientation", "horizontal"))
    if orientation == "vertical":
        width, height = "1080", "1920"
    elif orientation == "square":
        width, height = "1080", "1080"
    else:
        width, height = "1920", "1080"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = DOWNLOADS / f"nneka_{timestamp}_{job_id[:6]}.mp4"
    command = [
        sys.executable,
        str(ROOT / "clip_shuffle.py"),
        "--input-dir",
        str(video_dir),
        "--clip-seconds",
        "2.0",
        "--width",
        width,
        "--height",
        height,
        "--fps",
        str(args.get("fps", "30")),
        "--output",
        str(output_path),
    ]
    seed = str(args.get("seed", "")).strip()
    if seed:
        command.extend(["--seed", seed])
    if audio_path:
        command.extend(["--audio", str(audio_path)])

    add_log(job_id, f"Output: {output_path}")
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        add_log(job_id, line)
    exit_code = process.wait()

    if exit_code == 0 and output_path.exists():
        set_job(job_id, status="done", output_path=str(output_path))
        if IS_VERCEL:
            add_log(job_id, "Done. Use the download button before the cloud function instance expires.")
        else:
            add_log(job_id, "Done. File is in your Downloads folder.")
    else:
        set_job(job_id, status="error", error=f"Render failed with exit code {exit_code}.")
        add_log(job_id, f"Render failed with exit code {exit_code}.")


HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nneka</title>
  <style>
    :root {
      --bg: #f5f6f3;
      --ink: #161815;
      --muted: #62675f;
      --line: #d7d9d1;
      --panel: #ffffff;
      --accent: #087f6d;
      --accent-2: #284b63;
      --danger: #b42318;
      --shadow: 0 10px 30px rgba(20, 23, 18, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      letter-spacing: 0;
    }
    main {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(320px, 480px) 1fr;
      gap: 0;
    }
    .setup {
      padding: 28px;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    .status {
      padding: 28px;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 26px;
      line-height: 1.15;
    }
    .sub {
      margin: 0 0 22px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    form {
      display: grid;
      gap: 18px;
    }
    label {
      display: grid;
      gap: 8px;
      font-size: 13px;
      font-weight: 700;
    }
    input[type="file"],
    input[type="number"],
    select {
      width: 100%;
      border: 1px solid var(--line);
      background: #fbfcfa;
      border-radius: 6px;
      padding: 10px;
      color: var(--ink);
      font-size: 14px;
    }
    input[type="file"] {
      min-height: 46px;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .fixed {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      border: 1px solid var(--line);
      background: #eef5f2;
      border-radius: 6px;
      padding: 10px 12px;
      min-height: 42px;
      font-size: 14px;
    }
    .fixed strong {
      font-size: 18px;
    }
    button {
      appearance: none;
      border: 0;
      border-radius: 6px;
      padding: 13px 16px;
      background: var(--accent);
      color: white;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      min-height: 46px;
    }
    button:disabled {
      opacity: 0.55;
      cursor: wait;
    }
    .meter {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }
    .metric {
      padding: 16px;
      border-right: 1px solid var(--line);
      min-width: 0;
    }
    .metric:last-child { border-right: 0; }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 7px;
    }
    .metric strong {
      display: block;
      font-size: 16px;
      overflow-wrap: anywhere;
    }
    pre {
      flex: 1;
      min-height: 360px;
      margin: 0;
      padding: 16px;
      border: 1px solid #20241f;
      border-radius: 8px;
      background: #111411;
      color: #dfe8dc;
      overflow: auto;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.45;
    }
    .download {
      display: none;
      margin-top: 14px;
      color: white;
      background: var(--accent-2);
      text-decoration: none;
      border-radius: 6px;
      padding: 12px 14px;
      width: max-content;
      max-width: 100%;
      font-weight: 800;
    }
    .error {
      color: var(--danger);
      font-weight: 700;
      min-height: 18px;
      font-size: 13px;
    }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; }
      .setup { border-right: 0; border-bottom: 1px solid var(--line); }
      .meter { grid-template-columns: 1fr 1fr; }
      .metric:nth-child(2) { border-right: 0; }
      .metric:nth-child(1), .metric:nth-child(2) { border-bottom: 1px solid var(--line); }
    }
    @media (max-width: 520px) {
      .setup, .status { padding: 18px; }
      .row { grid-template-columns: 1fr; }
      .meter { grid-template-columns: 1fr; }
      .metric { border-right: 0; border-bottom: 1px solid var(--line); }
      .metric:last-child { border-bottom: 0; }
    }
  </style>
</head>
<body>
  <main>
    <section class="setup">
      <h1>Nneka</h1>
      <p class="sub">Use footage you own or are licensed to reuse. Every shot is cut to exactly 2.000 seconds.</p>
      <form id="jobForm">
        <label>
          Source videos
          <input name="videos" type="file" accept=".mp4,.mov,.mkv,.webm,.avi,.m4v,video/*" multiple required>
        </label>
        <label>
          Your audio
          <input name="audio" type="file" accept=".mp3,.wav,.m4a,.aac,.flac,.ogg,audio/*">
        </label>
        <div class="fixed">
          <span>Clip length</span>
          <strong>2.000s</strong>
        </div>
        <div class="row">
          <label>
            Format
            <select name="orientation">
              <option value="horizontal">16:9</option>
              <option value="vertical">9:16</option>
              <option value="square">1:1</option>
            </select>
          </label>
          <label>
            FPS
            <select name="fps">
              <option value="30">30</option>
              <option value="24">24</option>
              <option value="60">60</option>
            </select>
          </label>
        </div>
        <label>
          Shuffle seed
          <input name="seed" type="number" placeholder="optional">
        </label>
        <button id="submitBtn" type="submit">Create Video</button>
        <div id="formError" class="error"></div>
      </form>
    </section>
    <section class="status">
      <div class="meter">
        <div class="metric"><span>Status</span><strong id="statusText">ready</strong></div>
        <div class="metric"><span>Videos</span><strong id="videoCount">0</strong></div>
        <div class="metric"><span>Audio</span><strong id="audioName">none</strong></div>
        <div class="metric"><span>Export</span><strong id="exportName">Downloads</strong></div>
      </div>
      <pre id="log">Waiting for files.</pre>
      <a id="downloadLink" class="download" href="#">Download MP4</a>
    </section>
  </main>
  <script>
    const form = document.getElementById("jobForm");
    const button = document.getElementById("submitBtn");
    const statusText = document.getElementById("statusText");
    const log = document.getElementById("log");
    const formError = document.getElementById("formError");
    const videoCount = document.getElementById("videoCount");
    const audioName = document.getElementById("audioName");
    const exportName = document.getElementById("exportName");
    const downloadLink = document.getElementById("downloadLink");

    function updateCounts() {
      videoCount.textContent = form.videos.files.length;
      audioName.textContent = form.audio.files[0] ? form.audio.files[0].name : "none";
    }
    form.videos.addEventListener("change", updateCounts);
    form.audio.addEventListener("change", updateCounts);

    async function poll(jobId) {
      const res = await fetch(`/api/jobs/${jobId}`);
      const data = await res.json();
      statusText.textContent = data.status;
      log.textContent = data.log.length ? data.log.join("\n") : data.status;
      log.scrollTop = log.scrollHeight;
      if (data.output_path) {
        exportName.textContent = data.output_path.split(/[\\/]/).pop();
        downloadLink.href = `/download/${jobId}`;
        downloadLink.style.display = "inline-block";
      }
      if (data.status === "done" || data.status === "error") {
        button.disabled = false;
        button.textContent = "Create Video";
        return;
      }
      setTimeout(() => poll(jobId), 1200);
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      formError.textContent = "";
      downloadLink.style.display = "none";
      if (!form.videos.files.length) {
        formError.textContent = "Choose at least one source video.";
        return;
      }
      button.disabled = true;
      button.textContent = "Uploading...";
      statusText.textContent = "uploading";
      log.textContent = "Uploading files...";
      const body = new FormData(form);
      try {
        const res = await fetch("/api/run", { method: "POST", body });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Upload failed.");
        button.textContent = "Rendering...";
        poll(data.job_id);
      } catch (error) {
        formError.textContent = error.message;
        statusText.textContent = "error";
        button.disabled = false;
        button.textContent = "Create Video";
      }
    });
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.post("/api/run")
def api_run():
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    video_dir = job_dir / "videos"
    audio_dir = job_dir / "audio"
    job_dir.mkdir(parents=True, exist_ok=True)

    videos = save_uploads(request.files.getlist("videos"), video_dir, ALLOWED_VIDEO, "video")
    audio_files = save_uploads(request.files.getlist("audio"), audio_dir, ALLOWED_AUDIO, "audio")
    if not videos:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": "Upload at least one supported video file."}), 400

    job = Job(id=job_id)
    with jobs_lock:
        jobs[job_id] = job

    args = {
        "orientation": request.form.get("orientation", "horizontal"),
        "fps": request.form.get("fps", "30"),
        "seed": request.form.get("seed", ""),
    }
    if IS_VERCEL:
        run_job(job_id, video_dir, audio_files[0] if audio_files else None, args)
    else:
        thread = threading.Thread(
            target=run_job,
            args=(job_id, video_dir, audio_files[0] if audio_files else None, args),
            daemon=True,
        )
        thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        return jsonify(
            {
                "id": job.id,
                "status": job.status,
                "log": job.log,
                "output_path": job.output_path,
                "error": job.error,
            }
        )


@app.get("/download/<job_id>")
def download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or not job.output_path:
            return redirect(url_for("index"))
        output = Path(job.output_path)
    return send_file(output, as_attachment=True, download_name=output.name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)
