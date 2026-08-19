from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from google.cloud import texttospeech

ROOT = Path(__file__).resolve().parents[1]
SCENES_FILE = ROOT / "scripts" / "healthia_hero_20260819_scenes.json"
OUT = ROOT / "dist" / "healthia-hero-video" / "audio"
VOICE = "en-US-Chirp3-HD-Charon"


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ],
        text=True,
    ).strip()
    return float(out)


def srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def sentence_chunks(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    chunks: list[str] = []
    current = ""
    for part in parts:
        trial = f"{current} {part}".strip()
        if current and len(trial) > 118:
            chunks.append(current)
            current = part
        else:
            current = trial
    if current:
        chunks.append(current)
    return chunks


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = json.loads(SCENES_FILE.read_text(encoding="utf-8"))
    client = texttospeech.TextToSpeechClient()
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=VOICE)
    config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
    )

    durations: dict[str, float] = {}
    concat_lines: list[str] = []
    srt_entries: list[tuple[float, float, str]] = []
    cursor = 0.0

    for index, scene in enumerate(scenes, start=1):
        text = str(scene["text"]).strip()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=voice,
            audio_config=config,
        )
        path = OUT / f"{index:02d}-{scene['id']}.mp3"
        path.write_bytes(response.audio_content)
        duration = ffprobe_duration(path)
        durations[scene["id"]] = round(duration, 3)
        concat_lines.append(f"file '{path.resolve()}'")

        chunks = sentence_chunks(text)
        weights = [max(1, len(re.findall(r"\b[\w'-]+\b", chunk))) for chunk in chunks]
        total_weight = sum(weights) or 1
        local = cursor
        for chunk, weight in zip(chunks, weights):
            span = duration * (weight / total_weight)
            srt_entries.append((local, local + span, chunk))
            local += span
        cursor += duration

    concat = OUT / "concat.txt"
    concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    narration = OUT / "narration.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c:a", "libmp3lame", "-b:a", "192k", str(narration),
        ],
        check=True,
    )
    total = ffprobe_duration(narration)
    if total > 235.0:
        raise RuntimeError(f"narration exceeds safe contest budget: {total:.2f}s")

    (OUT / "scene-durations.json").write_text(
        json.dumps({"voice": VOICE, "scenes": durations, "total_seconds": round(total, 3)}, indent=2),
        encoding="utf-8",
    )

    srt = OUT / "captions.srt"
    lines: list[str] = []
    for i, (start, end, text) in enumerate(srt_entries, start=1):
        lines.extend([str(i), f"{srt_time(start)} --> {srt_time(end)}", text, ""])
    srt.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "voice": VOICE,
        "total_seconds": round(total, 3),
        "narration": str(narration),
        "captions": str(srt),
        "scene_count": len(scenes),
    }))


if __name__ == "__main__":
    main()
