from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path


def split_text(text: str, max_bytes: int = 2200) -> list[str]:
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return []
    if len(clean.encode("utf-8")) <= max_bytes:
        return [clean]
    sentences = []
    current = ""
    for token in clean.replace("? ", "?\n").replace("! ", "!\n").replace(". ", ".\n").splitlines():
        sentence = token.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate.encode("utf-8")) > max_bytes:
            sentences.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        sentences.append(current)
    return sentences


def access_token() -> str:
    completed = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return token


def synthesize_chunk(*, token: str, project: str, text: str, prompt: str, language_code: str, voice: str, model: str) -> bytes:
    payload = json.dumps(
        {
            "input": {"prompt": prompt, "text": text},
            "voice": {"languageCode": language_code, "name": voice, "modelName": model},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
        }
    ).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": project,
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = json.loads(response.read().decode("utf-8"))
            encoded = str(body.get("audioContent") or "")
            if not encoded:
                raise RuntimeError("Gemini TTS returned no audioContent")
            return base64.b64decode(encoded)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2500]
            # Retry only transient server/rate-limit responses. Client errors remain fail-closed.
            if exc.code not in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"Gemini TTS HTTP {exc.code}: {detail}") from exc
            last_error = RuntimeError(f"Gemini TTS transient HTTP {exc.code}: {detail}")
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc

        if attempt < 3:
            time.sleep(3 * attempt)

    raise RuntimeError(f"Gemini TTS failed after 3 attempts: {last_error}") from last_error


def merge_wavs(parts: list[bytes]) -> bytes:
    if not parts:
        raise RuntimeError("No WAV parts to merge")
    params = None
    frames: list[bytes] = []
    for data in parts:
        with wave.open(io.BytesIO(data), "rb") as source:
            current = (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
            if params is None:
                params = current
            elif current != params:
                raise RuntimeError("Gemini TTS chunks returned incompatible WAV parameters")
            frames.append(source.readframes(source.getnframes()))
    assert params is not None
    out = io.BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(params[0])
        target.setsampwidth(params[1])
        target.setframerate(params[2])
        target.setcomptype(params[3], "not compressed")
        for block in frames:
            target.writeframes(block)
    return out.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize a continuous Gemini TTS narration for a HealthIA demo.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--language-code", default="en-US")
    parser.add_argument("--voice", default="Charon")
    parser.add_argument("--model", default="gemini-2.5-pro-tts")
    parser.add_argument(
        "--style",
        default=(
            "Narrate in natural English with a warm adult male voice. Keep the voice calm, grounded, confident, "
            "and human, like a thoughtful healthcare professional explaining a real product to judges. Use a medium-low "
            "pitch, natural pauses, clear articulation, and an unhurried conversational pace. Avoid announcer energy, "
            "sales tone, melodrama, and robotic cadence. Pronounce Google product names and medical terms precisely."
        ),
    )
    args = parser.parse_args()
    if not args.project:
        raise SystemExit("--project or GOOGLE_CLOUD_PROJECT is required")
    text = Path(args.input).read_text(encoding="utf-8").strip()
    chunks = split_text(text)
    if not chunks:
        raise SystemExit("Narration input is empty")
    token = access_token()
    parts = [
        synthesize_chunk(
            token=token,
            project=args.project,
            text=chunk,
            prompt=args.style,
            language_code=args.language_code,
            voice=args.voice,
            model=args.model,
        )
        for chunk in chunks
    ]
    data = merge_wavs(parts)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    with wave.open(str(output), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
        metadata = {
            "provider": "Google Cloud Gemini TTS",
            "model": args.model,
            "voice": args.voice,
            "language_code": args.language_code,
            "chunks": len(chunks),
            "sample_rate_hz": wav.getframerate(),
            "channels": wav.getnchannels(),
            "duration_seconds": round(duration, 3),
            "audio_bytes": len(data),
        }
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
