from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = BASE_DIR / "bin"
TEMP_DIR = Path(tempfile.gettempdir()) / "fastcut"


def set_cache_dir(path: str) -> Path:

    global TEMP_DIR
    TEMP_DIR = Path(path) if path else Path(tempfile.gettempdir()) / "fastcut"
    return TEMP_DIR

VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv",
    ".ts", ".wmv", ".mpg", ".mpeg", ".3gp", ".m2ts",
}


def ffmpeg_exe() -> str:
    p = BIN_DIR / "ffmpeg.exe"
    if p.exists():
        return str(p)
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_exe() -> str:
    p = BIN_DIR / "ffprobe.exe"
    if p.exists():
        return str(p)
    return shutil.which("ffprobe") or "ffprobe"


def ensure_temp() -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def cleanup_temp() -> None:

    try:
        for f in ensure_temp().glob("*"):
            try:
                if f.is_file():
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass


def is_video(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def _run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=CREATE_NO_WINDOW,
        timeout=timeout,
    )


def probe(path: str) -> dict:
    cmd = [
        ffprobe_exe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    res = _run(cmd, timeout=40)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "无法解析该视频文件").strip().splitlines()[-1])
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        raise RuntimeError("该文件里没有视频轨道")

    duration = 0.0
    for candidate in (fmt.get("duration"), v.get("duration")):
        try:
            duration = float(candidate)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    fps = 0.0
    rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
    try:
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    size = 0
    try:
        size = int(fmt.get("size") or os.path.getsize(path))
    except (TypeError, ValueError, OSError):
        size = 0

    return {
        "duration": duration,
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": round(fps, 2),
        "vcodec": v.get("codec_name") or "",
        "acodec": (a or {}).get("codec_name") or "",
        "has_audio": a is not None,
        "size": size,
        "ext": Path(path).suffix.lower(),
    }


def _cache_key(path: str) -> str:
    try:
        st = os.stat(path)
        raw = f"{path}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        raw = path
    return hashlib.md5(raw.encode("utf-8", "ignore")).hexdigest()[:16]


def thumbnails(path: str, duration: float, count: int = 12,
               tw: int = 132, th: int = 74) -> dict:

    ensure_temp()
    key = _cache_key(path)
    sprite = TEMP_DIR / f"{key}_{count}.png"
    info = {"sprite": str(sprite), "count": count, "tw": tw, "th": th}
    if sprite.exists() and sprite.stat().st_size > 0:
        return info

    if duration <= 0:
        duration = 1.0
    interval = max(duration / count, 0.04)
    vf = (
        f"fps=1/{interval:.6f},"
        f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th},setsar=1,tile={count}x1"
    )
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", path, "-vf", vf, "-frames:v", "1", "-update", "1", str(sprite),
    ]
    res = _run(cmd, timeout=120)
    if res.returncode != 0 or not sprite.exists() or sprite.stat().st_size == 0:

        cmd = [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{min(1.0, duration / 3):.3f}", "-i", path,
            "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}",
            "-frames:v", "1", "-update", "1", str(sprite),
        ]
        _run(cmd, timeout=60)
        info["count"] = 1
    return info


def atempo_chain(speed: float) -> str:
    parts: list[str] = []
    x = speed
    while x > 2.0:
        parts.append("atempo=2.0")
        x /= 2.0
    while x < 0.5:
        parts.append("atempo=0.5")
        x /= 0.5
    parts.append(f"atempo={x:.4f}")
    return ",".join(parts)


def find_keyframe(path: str, target: float) -> float:

    if target <= 0.05:
        return 0.0
    lo = max(0.0, target - 15.0)
    cmd = [
        ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
        "-show_packets", "-show_entries", "packet=pts_time,flags",
        "-of", "csv=p=0",
        "-read_intervals", f"{lo:.3f}%{target + 0.5:.3f}", path,
    ]
    res = _run(cmd, timeout=30)
    best = 0.0
    for line in (res.stdout or "").splitlines():
        parts = line.strip().split(",")
        if len(parts) < 2 or "K" not in parts[1]:
            continue
        try:
            pts = float(parts[0])
        except ValueError:
            continue
        if pts <= target + 0.02:
            best = max(best, pts)
    return best


def build_export_args(src: str, dst: str, start: float, dur: float, *,
                      accurate: bool, mute: bool, speed: float,
                      has_audio: bool) -> list[str]:
    args = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "info", "-y",
        "-ss", f"{start:.3f}", "-i", src,
    ]
    if accurate:
        vf = []
        if abs(speed - 1.0) > 0.001:
            vf.append(f"setpts=PTS/{speed:.4f}")
        if vf:
            args += ["-vf", ",".join(vf)]
        if not mute and has_audio and abs(speed - 1.0) > 0.001:
            args += ["-af", atempo_chain(speed)]

        args += ["-t", f"{dur / max(speed, 0.01):.3f}"]
        if mute or not has_audio:
            args += ["-an"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-pix_fmt", "yuv420p"]
        if not mute and has_audio:
            args += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
        args += ["-movflags", "+faststart"]
    else:
        args += ["-t", f"{dur:.3f}"]
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    args += [dst]
    return args


def rotate_filters(rotate: int, mirror: bool) -> list[str]:

    out: list[str] = []
    if rotate == 90:
        out.append("transpose=1")
    elif rotate == 180:
        out += ["hflip", "vflip"]
    elif rotate == 270:
        out.append("transpose=2")
    if mirror:
        out.append("hflip")
    return out


def needs_reencode(segments_ms, *, accurate: bool, speed: float,
                   rotate: int, mirror: bool, volume: float) -> bool:

    return (accurate or len(segments_ms) > 1 or abs(speed - 1.0) > 0.001
            or rotate % 360 != 0 or mirror or abs(volume - 1.0) > 0.001)


def build_concat_args(src: str, dst: str, segments_ms, *, mute: bool,
                      speed: float, has_audio: bool, rotate: int = 0,
                      mirror: bool = False, volume: float = 1.0,
                      crf: int = 20) -> list[str]:

    segs = sorted((a / 1000.0, b / 1000.0) for a, b in segments_ms)
    base = segs[0][0]
    args = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "info", "-y",
        "-ss", f"{base:.3f}", "-i", src,
    ]
    keep_audio = has_audio and not mute
    graph: list[str] = []
    for i, (a, b) in enumerate(segs):
        graph.append(
            f"[0:v]trim=start={a - base:.3f}:end={b - base:.3f},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
        if keep_audio:
            graph.append(
                f"[0:a]atrim=start={a - base:.3f}:end={b - base:.3f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )
    n = len(segs)
    if keep_audio:
        graph.append(
            "".join(f"[v{i}][a{i}]" for i in range(n))
            + f"concat=n={n}:v=1:a=1[vc][ac]"
        )
        vtag, atag = "[vc]", "[ac]"
    else:
        graph.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
        vtag, atag = "[vc]", None

    vf = rotate_filters(rotate, mirror)
    if abs(speed - 1.0) > 0.001:
        vf.append(f"setpts=PTS/{speed:.4f}")
    if vf:
        graph.append(f"{vtag}{','.join(vf)}[vs]")
        vtag = "[vs]"

    if atag:
        af = []
        if abs(speed - 1.0) > 0.001:
            af.append(atempo_chain(speed))
        if abs(volume - 1.0) > 0.001:
            af.append(f"volume={volume:.3f}")
        if af:
            graph.append(f"{atag}{','.join(af)}[as]")
            atag = "[as]"

    args += ["-filter_complex", ";".join(graph), "-map", vtag]
    if atag:
        args += ["-map", atag]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(int(crf)),
             "-pix_fmt", "yuv420p"]
    if atag:
        args += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    args += ["-movflags", "+faststart", dst]
    return args


def build_proxy_args(src: str, dst: str, height: int = 720) -> list[str]:
    return [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "info", "-y",
        "-i", src,
        "-vf", f"scale=-2:{height}:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", dst,
    ]


TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def run_ffmpeg(args: list[str], total_seconds: float, on_progress, should_cancel):

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=CREATE_NO_WINDOW,
    )
    tail: list[str] = []
    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            if should_cancel():
                proc.kill()
                return False, True, ""
            tail.append(line.rstrip())
            if len(tail) > 40:
                tail.pop(0)
            m = TIME_RE.search(line)
            if m and total_seconds > 0:
                h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                done = h * 3600 + mi * 60 + s
                pct = max(0, min(99, int(done / total_seconds * 100)))
                on_progress(pct)
        proc.wait(timeout=30)
    except Exception as exc:
        try:
            proc.kill()
        except OSError:
            pass
        return False, False, str(exc)
    if proc.returncode == 0:
        on_progress(100)
        return True, False, ""
    msg = "\n".join([l for l in tail if l.strip()][-4:]) or "ffmpeg 处理失败"
    return False, False, msg
