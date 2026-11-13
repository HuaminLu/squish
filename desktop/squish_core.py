"""Compression core. Mirrors lib/plan.dart + lib/engine.dart in the Android app.

Two-pass x264 aimed a few percent under the limit, with the resolution picked
from a bits-per-pixel budget, then verified on disk and tightened if needed.
Optional edits: speed (0.25x-4x), trim (start/end), centre crop to an aspect.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from typing import Callable, Optional

HEADROOM = 0.975          # aim 2.5 % under the limit
MIN_BITS_PER_PIXEL = 0.035
LADDER = [2160, 1440, 1080, 720, 540, 480, 360, 240]
PRESET = "medium"         # desktop: quality-first, still ~4x realtime for 1080p
MAX_VIDEO_KBPS = 30000
CROPS = ["", "16:9", "1:1", "9:16", "4:3"]
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts", ".3gp", ".wmv", ".flv", ".mts"}

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def ffmpeg_path() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    p = os.path.join(base, "bin", exe)
    if os.path.exists(p):
        return p
    p = os.path.join(base, exe)
    return p if os.path.exists(p) else exe


@dataclass
class SourceInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    audio_codec: str = ""
    audio_kbps: int = 0
    audio_channels: int = 2


@dataclass
class Edit:
    speed: float = 1.0   # 0.25 .. 4
    start: float = 0.0   # seconds
    end: float = 0.0     # seconds, 0 = until the end
    crop: str = ""       # "", "16:9", "1:1", "9:16", "4:3"

    def span(self, duration: float) -> tuple[float, float]:
        s = min(max(self.start, 0.0), duration)
        e = self.end if self.end > 0 else duration
        e = min(max(e, s + 0.5), duration) if duration > 0.5 else duration
        return s, e

    def trimmed(self, duration: float) -> bool:
        s, e = self.span(duration)
        return s > 0.05 or e < duration - 0.05

    def is_default(self, duration: float) -> bool:
        return abs(self.speed - 1) < 1e-6 and not self.crop and not self.trimmed(duration)

    def tag(self, duration: float) -> str:
        parts = []
        if abs(self.speed - 1) > 1e-6:
            parts.append(f"{self.speed:g}x")
        if self.trimmed(duration):
            parts.append("cut")
        if self.crop:
            parts.append(self.crop.replace(":", "x"))
        return "".join(f"-{p}" for p in parts)


@dataclass
class Plan:
    limit_bytes: int
    video_kbps: int
    audio_kbps: int
    audio_copy: bool
    mono: bool
    out_height: int   # 0 = keep
    out_fps: float    # 0 = keep
    out_duration: float = 0.0
    crop_w: int = 0
    crop_h: int = 0


def crop_rect(w: int, h: int, aspect: str) -> Optional[tuple[int, int, int, int]]:
    """Centre crop (cw, ch, x, y) to the given 'W:H' aspect, even dimensions."""
    if not aspect:
        return None
    aw, ah = (float(x) for x in aspect.split(":"))
    a = aw / ah
    if w / h > a:
        ch, cw = h, int(round(h * a))
    else:
        cw, ch = w, int(round(w / a))
    cw, ch = cw - cw % 2, ch - ch % 2
    if cw >= w and ch >= h:
        return None
    return cw, ch, (w - cw) // 2, (h - ch) // 2


def _ratio(s) -> Optional[float]:
    if not s:
        return None
    if "/" in str(s):
        n, d = str(s).split("/", 1)
        try:
            n, d = float(n), float(d)
        except ValueError:
            return None
        return n / d if d else None
    try:
        return float(s)
    except ValueError:
        return None


def probe(path: str) -> SourceInfo:
    """Parse `ffmpeg -i` output (keeps the bundle to a single ffmpeg.exe)."""
    r = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", path],
                       capture_output=True, text=True, errors="replace", creationflags=CREATE_NO_WINDOW)
    txt = r.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", txt)
    if not m:
        raise RuntimeError("Could not read video duration")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    if duration <= 0:
        raise RuntimeError("Could not read video duration")
    vm = re.search(r"Stream #\d+:\d+.*?: Video: (.*)", txt)
    if not vm:
        raise RuntimeError("No video stream found")
    vline = vm.group(1)
    dm = re.search(r"(?<![\dx])(\d{2,5})x(\d{2,5})(?!\d)", vline)
    if not dm:
        raise RuntimeError("Could not read video size")
    width, height = int(dm.group(1)), int(dm.group(2))
    fm = re.search(r"([\d.]+) fps", vline)
    fps = float(fm.group(1)) if fm else 30.0
    if fps <= 0 or fps > 240:
        fps = 30.0
    am = re.search(r"Stream #\d+:\d+.*?: Audio: (\w+).*?(\d+) Hz, ([^,]+)(?:,.*?(\d+) kb/s)?", txt)
    has_audio = am is not None
    codec, kbps, ch = "", 0, 2
    if am:
        codec = am.group(1).lower()
        layout = am.group(3).strip()
        ch = 1 if layout.startswith("mono") else 2
        kbps = int(am.group(4)) if am.group(4) else 0
    return SourceInfo(duration=duration, width=width, height=height, fps=fps,
                      has_audio=has_audio, audio_codec=codec, audio_kbps=kbps, audio_channels=ch)


def make_plan(src: SourceInfo, target_mb: float, edit: Optional[Edit] = None) -> Plan:
    edit = edit or Edit()
    s, e = edit.span(src.duration)
    out_duration = max((e - s) / edit.speed, 0.1)
    cr = crop_rect(src.width, src.height, edit.crop)
    src_w, src_h = (cr[0], cr[1]) if cr else (src.width, src.height)

    limit_bytes = int(target_mb * 1_000_000)
    total_kbps = limit_bytes * 8 * HEADROOM / out_duration / 1000.0

    audio_kbps, mono, audio_copy = 0, False, False
    if src.has_audio:
        if total_kbps >= 1400:
            audio_kbps = 128
        elif total_kbps >= 800:
            audio_kbps = 96
        elif total_kbps >= 400:
            audio_kbps = 64
        else:
            audio_kbps, mono = 48, True
        if src.audio_channels <= 1:
            mono = True
        if abs(edit.speed - 1) < 1e-6 and src.audio_codec == "aac" and 0 < src.audio_kbps <= audio_kbps + 8:
            audio_copy, audio_kbps = True, src.audio_kbps

    video_kbps = int(total_kbps * 0.99 - audio_kbps)
    video_kbps = min(max(video_kbps, 40), MAX_VIDEO_KBPS)

    fps, out_fps = src.fps, 0.0
    if fps > 60:
        out_fps, fps = 60.0, 60.0

    rungs = [src_h] + [h for h in LADDER if h < src_h]
    chosen = src_h
    for h in rungs:
        w = src_w * h / src_h
        chosen = h
        if video_kbps * 1000.0 / (w * h * fps) >= MIN_BITS_PER_PIXEL:
            break
    out_height = 0 if chosen == src_h else chosen

    if fps > 30:
        w = src_w * chosen / src_h
        if video_kbps * 1000.0 / (w * chosen * fps) < MIN_BITS_PER_PIXEL:
            out_fps = 30.0

    return Plan(limit_bytes, video_kbps, audio_kbps, audio_copy, mono, out_height, out_fps,
                out_duration, cr[0] if cr else 0, cr[1] if cr else 0)


def video_filters(src: SourceInfo, edit: Edit, plan: Plan) -> list[str]:
    vf = []
    cr = crop_rect(src.width, src.height, edit.crop)
    if cr:
        vf.append(f"crop={cr[0]}:{cr[1]}:{cr[2]}:{cr[3]}")
    if abs(edit.speed - 1) > 1e-6:
        vf.append(f"setpts=PTS/{edit.speed:g}")
    if plan.out_height:
        vf.append(f"scale=-2:{plan.out_height}")
    if plan.out_fps:
        vf.append(f"fps={plan.out_fps:g}")
    return vf


def audio_filters(edit: Edit) -> list[str]:
    f = edit.speed
    if abs(f - 1) < 1e-6:
        return []
    chain = []
    while f > 2.0:
        chain.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        chain.append("atempo=0.5")
        f *= 2.0
    chain.append(f"atempo={f:g}")
    return chain


def fmt_mb(b: int) -> str:
    return f"{b / 1_000_000:.1f} MB"


def fmt_time(s: float) -> str:
    s = max(int(round(s)), 0)
    return f"{s // 60}:{s % 60:02d}"


class Cancelled(Exception):
    pass


@dataclass
class Progress:
    stage: str
    fraction: float
    speed: float


class Job:
    """One compression run. `cancel()` from any thread."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._cancel = False

    def cancel(self):
        self._cancel = True
        p = self._proc
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def thumbnail(self, src: str, at: float, out_path: str, crop: str = "",
                  src_size: Optional[tuple[int, int]] = None, height: int = 480) -> bool:
        vf = []
        if crop and src_size:
            cr = crop_rect(src_size[0], src_size[1], crop)
            if cr:
                vf.append(f"crop={cr[0]}:{cr[1]}:{cr[2]}:{cr[3]}")
        vf.append(f"scale=-2:{height}")
        r = subprocess.run(
            [ffmpeg_path(), "-y", "-v", "error", "-ss", f"{max(at, 0):.2f}", "-i", src, "-frames:v", "1",
             "-vf", ",".join(vf), "-q:v", "4", out_path],
            capture_output=True, creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0 and os.path.exists(out_path)

    def _run(self, args: list[str], duration: float, stage: str, lo: float, hi: float,
             on_progress: Callable[[Progress], None]):
        if self._cancel:
            raise Cancelled()
        cmd = [ffmpeg_path(), "-y", "-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "error"] + args
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, creationflags=CREATE_NO_WINDOW)
        speed = 0.0
        for line in self._proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    t = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                f = min(max(t / duration, 0.0), 1.0)
                on_progress(Progress(stage, lo + (hi - lo) * f, speed))
            elif line.startswith("speed="):
                m = re.search(r"([\d.]+)x", line)
                if m:
                    speed = float(m.group(1))
        err = self._proc.stderr.read() if self._proc.stderr else ""
        rc = self._proc.wait()
        if self._cancel:
            raise Cancelled()
        if rc != 0:
            tail = "\n".join(err.strip().splitlines()[-6:])
            raise RuntimeError(f"ffmpeg failed:\n{tail}")

    def squish(self, src: str, src_info: SourceInfo, target_mb: float, out_dir: str,
               on_progress: Callable[[Progress], None], edit: Optional[Edit] = None
               ) -> tuple[str, int, Plan, float]:
        t0 = time.time()
        edit = edit or Edit()
        plan = make_plan(src_info, target_mb, edit)
        tmp = tempfile.mkdtemp(prefix="squish_")
        log = os.path.join(tmp, "pl")
        tmp_out = os.path.join(tmp, "out.mp4")

        s, e = edit.span(src_info.duration)
        # -ss/-t as INPUT options: they bound what is read, so speed changes do not pull extra source.
        in_args = (["-ss", f"{s:.3f}"] if s > 0.05 else []) +                   (["-t", f"{e - s:.3f}"] if edit.trimmed(src_info.duration) else []) + ["-i", src]
        vf = video_filters(src_info, edit, plan)
        vf_args = ["-vf", ",".join(vf)] if vf else []
        af = audio_filters(edit)
        af_args = ["-af", ",".join(af)] if af else []

        def common(p: Plan) -> list[str]:
            return vf_args + ["-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-c:v", "libx264",
                              "-preset", PRESET, "-profile:v", "high",
                              "-b:v", f"{p.video_kbps}k", "-maxrate", f"{int(p.video_kbps * 1.5)}k",
                              "-bufsize", f"{p.video_kbps * 3}k", "-passlogfile", log]

        def audio(p: Plan) -> list[str]:
            if p.audio_kbps == 0:
                return ["-an"]
            if p.audio_copy:
                return ["-c:a", "copy"]
            return af_args + ["-c:a", "aac", "-b:a", f"{p.audio_kbps}k"] + (["-ac", "1"] if p.mono else [])

        null = "NUL" if os.name == "nt" else "/dev/null"
        self._run(in_args + common(plan) + ["-pass", "1", "-an", "-f", "null", null],
                  plan.out_duration, "Analyzing", 0.0, 0.45, on_progress)

        size = 0
        for attempt in range(3):
            self._run(in_args + common(plan) + ["-pass", "2"] + audio(plan) +
                      ["-movflags", "+faststart", tmp_out],
                      plan.out_duration, "Encoding" if attempt == 0 else "Tightening", 0.45, 0.98, on_progress)
            size = os.path.getsize(tmp_out)
            if size < plan.limit_bytes:
                break
            plan = replace(plan, video_kbps=int(plan.video_kbps * plan.limit_bytes * 0.96 / size))
        if size >= plan.limit_bytes:
            raise RuntimeError("Could not get under the limit. Try a bigger size.")

        on_progress(Progress("Saving", 0.99, 0))
        base = os.path.splitext(os.path.basename(src))[0]
        tag = (f"{int(target_mb)}mb" if float(target_mb).is_integer() else f"{target_mb:g}mb") + edit.tag(src_info.duration)
        os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, f"{base}-{tag}.mp4")
        n = 1
        while os.path.exists(dst):
            dst = os.path.join(out_dir, f"{base}-{tag} ({n}).mp4")
            n += 1
        os.replace(tmp_out, dst)
        try:
            for f in os.listdir(tmp):
                os.remove(os.path.join(tmp, f))
            os.rmdir(tmp)
        except OSError:
            pass
        return dst, size, plan, time.time() - t0


# ---------------- recent videos (gallery strip) ----------------

def recent_videos(folders: list[str], limit: int = 24) -> list[str]:
    seen, items = set(), []
    for d in folders:
        if not d or not os.path.isdir(d):
            continue
        try:
            for n in os.listdir(d):
                p = os.path.join(d, n)
                if os.path.splitext(n)[1].lower() in VIDEO_EXTS and os.path.isfile(p):
                    k = os.path.normcase(p)
                    if k not in seen:
                        seen.add(k)
                        items.append(p)
        except OSError:
            pass
    items.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return items[:limit]


def thumb_cache_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "Squish", "thumbs")
    os.makedirs(d, exist_ok=True)
    return d


def cached_thumb(path: str, height: int = 96) -> Optional[str]:
    """Small thumbnail for the recent strip, cached by path + mtime + size."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = hashlib.sha1(f"{os.path.normcase(path)}|{st.st_mtime_ns}|{st.st_size}|{height}".encode()).hexdigest()
    out = os.path.join(thumb_cache_dir(), key + ".jpg")
    if os.path.exists(out):
        return out
    r = subprocess.run(
        [ffmpeg_path(), "-y", "-v", "error", "-ss", "1", "-i", path, "-frames:v", "1",
         "-vf", f"scale=-2:{height}", "-q:v", "6", out],
        capture_output=True, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(out):
        r = subprocess.run(
            [ffmpeg_path(), "-y", "-v", "error", "-i", path, "-frames:v", "1",
             "-vf", f"scale=-2:{height}", "-q:v", "6", out],
            capture_output=True, creationflags=CREATE_NO_WINDOW)
    return out if os.path.exists(out) else None


if __name__ == "__main__":  # quick CLI: python squish_core.py in.mp4 20 outdir [speed start end crop]
    src, mb, outdir = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    ed = Edit()
    if len(sys.argv) > 4:
        ed = Edit(speed=float(sys.argv[4]), start=float(sys.argv[5]), end=float(sys.argv[6]),
                  crop=sys.argv[7] if len(sys.argv) > 7 else "")
    info = probe(src)
    print(info)
    print(make_plan(info, mb, ed))
    job = Job()
    last = [0]

    def pr(p: Progress):
        if time.time() - last[0] > 1:
            last[0] = time.time()
            print(f"{p.stage} {p.fraction*100:5.1f}% {p.speed:.1f}x")

    dst, size, plan, secs = job.squish(src, info, mb, outdir, pr, ed)
    print(dst, size, fmt_mb(size), f"{secs:.1f}s")
