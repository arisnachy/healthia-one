from __future__ import annotations

import json
import subprocess
from pathlib import Path

from google.cloud import texttospeech

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / "scripts" / "live_product_film_narration_20260819.json"
OUT = ROOT / "dist" / "live-product-film" / "audio"
VOICE = "en-US-Chirp3-HD-Charon"


def duration(path: Path) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ], text=True).strip())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = json.loads(SCENES.read_text(encoding="utf-8"))
    client = texttospeech.TextToSpeechClient()
    concat = []
    rows = []
    cursor = 0.0
    for index, scene in enumerate(scenes, start=1):
        response = client.synthesize_speech(request={
            "input": texttospeech.SynthesisInput(text=scene["text"]),
            "voice": texttospeech.VoiceSelectionParams(language_code="en-US", name=VOICE),
            "audio_config": texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.03,
            ),
        })
        path = OUT / f"scene-{index:02d}-{scene['id']}.mp3"
        path.write_bytes(response.audio_content)
        seconds = duration(path)
        rows.append({"id": scene["id"], "start": round(cursor, 3), "duration": round(seconds, 3), "end": round(cursor + seconds, 3)})
        cursor += seconds
        concat.append(f"file '{path.resolve()}'")
    concat_path = OUT / "concat.txt"
    concat_path.write_text("\n".join(concat) + "\n", encoding="utf-8")
    master = OUT / "narration.mp3"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", str(master)], check=True)
    total = duration(master)
    manifest = {"voice": VOICE, "total_seconds": round(total, 3), "scenes": rows}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not 140 <= total <= 225:
        raise SystemExit(f"Narration outside director window: {total:.3f}s")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
