from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from google.cloud import texttospeech

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / "scripts" / "guardian_director_scenes_20260819.json"
OUT = ROOT / "dist" / "guardian-director-cut" / "audio"
VOICE = "en-US-Chirp3-HD-Charon"
MAX_CAPTION_WORDS = 10


def probe_seconds(path: Path) -> float:
    value = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(value)


def stamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def caption_chunks(text: str) -> list[str]:
    """Break narration into short caption phrases instead of scene-long blocks."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        strong_break = bool(re.search(r"[.!?;:]$", word))
        soft_break = bool(re.search(r",$", word)) and len(current) >= 6
        if len(current) >= MAX_CAPTION_WORDS or (strong_break and len(current) >= 4) or soft_break:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def two_lines(text: str) -> str:
    words = text.split()
    if len(words) <= 6:
        return text
    split_at = (len(words) + 1) // 2
    return " ".join(words[:split_at]) + "\n" + " ".join(words[split_at:])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = json.loads(SCENES.read_text(encoding="utf-8"))
    client = texttospeech.TextToSpeechClient()
    rows = []
    concat_lines = []
    cursor = 0.0
    srt: list[str] = []
    caption_index = 1

    for index, scene in enumerate(scenes, start=1):
        response = client.synthesize_speech(
            request={
                "input": texttospeech.SynthesisInput(text=scene["text"]),
                "voice": texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name=VOICE,
                ),
                "audio_config": texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=0.98,
                ),
            }
        )
        path = OUT / f"scene-{index:02d}-{scene['id']}.mp3"
        path.write_bytes(response.audio_content)
        duration = probe_seconds(path)
        start = cursor
        end = cursor + duration

        chunks = caption_chunks(scene["text"])
        if not chunks or any(len(chunk.split()) > MAX_CAPTION_WORDS for chunk in chunks):
            raise RuntimeError(f"unsafe caption segmentation for scene {scene['id']}")
        total_words = sum(len(chunk.split()) for chunk in chunks)
        chunk_cursor = start
        for chunk_number, chunk in enumerate(chunks):
            words_here = len(chunk.split())
            if chunk_number == len(chunks) - 1:
                chunk_end = end
            else:
                chunk_end = min(end, chunk_cursor + duration * (words_here / total_words))
            srt.extend(
                [
                    str(caption_index),
                    f"{stamp(chunk_cursor)} --> {stamp(chunk_end)}",
                    two_lines(chunk),
                    "",
                ]
            )
            caption_index += 1
            chunk_cursor = chunk_end

        rows.append(
            {
                "index": index,
                "id": scene["id"],
                "duration": round(duration, 3),
                "start": round(start, 3),
                "end": round(end, 3),
                "caption_chunks": len(chunks),
                "text": scene["text"],
            }
        )
        concat_lines.append(f"file '{path.resolve()}'")
        cursor = end

    concat = OUT / "concat.txt"
    concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    master = OUT / "narration.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(master)],
        check=True,
    )
    (OUT / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
    payload = {
        "voice": VOICE,
        "total_seconds": round(probe_seconds(master), 3),
        "caption_count": caption_index - 1,
        "max_caption_words": MAX_CAPTION_WORDS,
        "scenes": rows,
    }
    (OUT / "scene-durations.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if payload["total_seconds"] > 235:
        raise SystemExit(f"Narration too long: {payload['total_seconds']} seconds")
    if payload["caption_count"] < 30:
        raise SystemExit("Caption segmentation is unexpectedly sparse")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
