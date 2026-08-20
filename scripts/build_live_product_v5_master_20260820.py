from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "dist" / "live-product-film"
VIDEO_DIR = BASE / "video"
AUDIO = BASE / "audio" / "narration.mp3"
TRIMMED = BASE / "live-product-v5-smart-trim.mp4"
FINAL = BASE / "HealthIA-ONE-LIVE-PRODUCT-V5-AUTONOMOUS-FINAL.mp4"
REPORT = BASE / "trim-report-v5.json"


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)


def ffprobe_duration(path: Path) -> float:
    p = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ], capture=True)
    value = float(p.stdout.strip())
    if value <= 0:
        raise RuntimeError(f"invalid duration for {path}: {value}")
    return value


def detect_freezes(raw: Path, threshold: str, minimum_seconds: float = 12.0) -> list[tuple[float, float]]:
    p = subprocess.run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(raw),
        "-vf", f"freezedetect=n={threshold}:d={minimum_seconds}",
        "-f", "null", "-",
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"freezedetect failed ({threshold}): {p.stderr[-3000:]}")

    starts: list[float] = []
    intervals: list[tuple[float, float]] = []
    for line in p.stderr.splitlines():
        m = re.search(r"freeze_start:\s*([0-9.]+)", line)
        if m:
            starts.append(float(m.group(1)))
            continue
        m = re.search(r"freeze_end:\s*([0-9.]+)", line)
        if m and starts:
            start = starts.pop(0)
            end = float(m.group(1))
            if end > start:
                intervals.append((start, end))
    return intervals


def removable_middle(intervals: list[tuple[float, float]], *, edge_keep: float = 2.0) -> list[tuple[float, float]]:
    cuts: list[tuple[float, float]] = []
    for start, end in intervals:
        a = start + edge_keep
        b = end - edge_keep
        if b - a >= 6.0:
            cuts.append((a, b))
    return cuts


def merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 0.05:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(a, b) for a, b in merged]


def complement(duration: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in cuts:
        start = max(0.0, min(duration, start))
        end = max(0.0, min(duration, end))
        if start > cursor + 0.05:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration - 0.05:
        keep.append((cursor, duration))
    return keep


def estimated_duration(duration: float, cuts: list[tuple[float, float]]) -> float:
    return duration - sum(max(0.0, b - a) for a, b in cuts)


def choose_trim_plan(raw: Path, raw_duration: float) -> dict:
    candidates = []
    # Start strict and increase tolerance only if needed. Intentional holds in the
    # recorder are <=8s; only freezes >=12s are eligible for removal.
    for threshold in ("-55dB", "-50dB", "-45dB", "-40dB", "-35dB"):
        freezes = detect_freezes(raw, threshold)
        cuts = merge_intervals(removable_middle(freezes))
        estimate = estimated_duration(raw_duration, cuts)
        candidates.append({
            "threshold": threshold,
            "freezes": freezes,
            "cuts": cuts,
            "estimated_trimmed_seconds": estimate,
        })
        # Prefer the least aggressive plan that lands near the narrated target.
        if 165.0 <= estimate <= 225.0:
            return candidates[-1]

    viable = [c for c in candidates if 145.0 <= c["estimated_trimmed_seconds"] <= 245.0]
    if viable:
        return min(viable, key=lambda c: abs(c["estimated_trimmed_seconds"] - 198.0))

    diagnostic = [{"threshold": c["threshold"], "estimate": round(c["estimated_trimmed_seconds"], 3)} for c in candidates]
    raise RuntimeError(f"no safe smart-trim plan found: {diagnostic}")


def render_trimmed(raw: Path, keep: list[tuple[float, float]]) -> None:
    if not keep:
        raise RuntimeError("smart trim produced no keep intervals")

    script = BASE / "smart-trim-v5.filter"
    lines: list[str] = []
    labels: list[str] = []
    for i, (start, end) in enumerate(keep):
        label = f"v{i}"
        labels.append(f"[{label}]")
        lines.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[{label}];")
    lines.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vout]")
    script.write_text("\n".join(lines), encoding="utf-8")

    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(raw), "-filter_complex_script", str(script),
        "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-pix_fmt", "yuv420p", str(TRIMMED),
    ])


def render_final(trimmed_duration: float, audio_duration: float) -> float:
    factor = audio_duration / trimmed_duration
    # Small editorial speed adjustment is acceptable; large acceleration is not.
    if not 0.80 <= factor <= 1.22:
        raise RuntimeError(
            f"smart trim still requires unsafe timing factor {factor:.3f} "
            f"(trimmed={trimmed_duration:.3f}s audio={audio_duration:.3f}s)"
        )
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(TRIMMED), "-i", str(AUDIO),
        "-filter_complex",
        f"[0:v]setpts={factor:.9f}*PTS,scale=1920:1080:flags=lanczos,fps=30[v];"
        "[1:a]loudnorm=I=-16:LRA=7:TP=-1.5[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
        "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(FINAL),
    ])
    return factor


def main() -> None:
    raws = sorted(VIDEO_DIR.glob("*.webm"))
    if not raws:
        raise RuntimeError("no Playwright raw video found")
    raw = raws[0]
    if not AUDIO.exists() or AUDIO.stat().st_size == 0:
        raise RuntimeError("narration audio missing")

    raw_duration = ffprobe_duration(raw)
    audio_duration = ffprobe_duration(AUDIO)
    plan = choose_trim_plan(raw, raw_duration)
    cuts = plan["cuts"]
    keep = complement(raw_duration, cuts)
    render_trimmed(raw, keep)
    trimmed_duration = ffprobe_duration(TRIMMED)
    factor = render_final(trimmed_duration, audio_duration)
    final_duration = ffprobe_duration(FINAL)

    payload = {
        "schema": "healthia-live-product-smart-trim/v1",
        "raw_file": str(raw.relative_to(ROOT)),
        "raw_duration_seconds": round(raw_duration, 3),
        "audio_duration_seconds": round(audio_duration, 3),
        "freeze_threshold": plan["threshold"],
        "freeze_minimum_seconds": 12.0,
        "edge_keep_seconds": 2.0,
        "removed_intervals": [[round(a, 3), round(b, 3)] for a, b in cuts],
        "removed_seconds": round(sum(b - a for a, b in cuts), 3),
        "trimmed_duration_seconds": round(trimmed_duration, 3),
        "final_timing_factor": round(factor, 6),
        "final_duration_seconds": round(final_duration, 3),
        "policy": "remove only long static waits; preserve live application interactions",
    }
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"FINAL_VIDEO={FINAL}")


if __name__ == "__main__":
    main()
