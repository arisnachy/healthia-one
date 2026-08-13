from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from healthia_one.education_video_models import EducationFact, EducationVideoPlan, NarrationAudio


ROOT = Path(__file__).resolve().parents[1]


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        left, _, right, _ = draw.textbbox((0, 0), candidate, font=font)
        if right - left <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


class EducationVideoRenderer:
    """Build a real MP4 from controlled HealthIA cards, narration and optional Veo footage."""

    width = 1280
    height = 720

    def _slide(self, path: Path, *, eyebrow: str, heading: str, body: str, index: int, count: int) -> None:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (self.width, self.height), (245, 248, 252))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((55, 48, 1225, 672), radius=34, fill=(255, 255, 255), outline=(218, 227, 239), width=2)
        draw.rounded_rectangle((85, 84, 330, 126), radius=18, fill=(232, 241, 253))
        draw.text((103, 95), eyebrow.upper()[:35], font=_font(18, True), fill=(31, 92, 170))
        draw.text((88, 157), "HealthIA ONE", font=_font(24, True), fill=(29, 61, 104))
        y = 217
        for line in _wrap(draw, heading, _font(48, True), 1030)[:3]:
            draw.text((88, y), line, font=_font(48, True), fill=(18, 35, 62))
            y += 60
        y += 18
        for line in _wrap(draw, body, _font(29), 1030)[:7]:
            draw.text((88, y), line, font=_font(29), fill=(78, 96, 122))
            y += 42
        progress = max(1, int(1045 * (index + 1) / max(count, 1)))
        draw.rounded_rectangle((88, 615, 1133, 626), radius=6, fill=(231, 237, 245))
        draw.rounded_rectangle((88, 615, 88 + progress, 626), radius=6, fill=(55, 102, 165))
        draw.text((88, 643), f"{index + 1}/{count}", font=_font(17, True), fill=(105, 121, 145))
        draw.text((882, 643), "Educación clínica · privado", font=_font(17), fill=(105, 121, 145))
        image.save(path, format="PNG")

    @staticmethod
    def _run(args: list[str]) -> None:
        completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0:
            tail = completed.stderr.decode("utf-8", errors="replace")[-1800:]
            raise RuntimeError(f"ffmpeg failed while rendering HealthIA Explain: {tail}")

    def render(
        self,
        *,
        title: str,
        topic: str,
        facts: list[EducationFact],
        plan: EducationVideoPlan,
        narration: NarrationAudio,
        target_duration_seconds: int,
        veo_clip: bytes | None = None,
    ) -> bytes:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory(prefix="healthia-explain-") as tmp:
            root = Path(tmp)
            audio_path = root / f"narration{narration.suffix}"
            audio_path.write_bytes(narration.data)

            specs: list[tuple[str, str, str, bool]] = [
                ("HEALTHIA EXPLAIN", title, f"Una explicación visual sobre {topic}.", False)
            ]
            if facts:
                fact_body = "  •  ".join(f"{item.label}: {item.value}" for item in facts[:4])
                specs.append(("TU INFORMACIÓN", "Lo que consta en tu expediente", fact_body, False))
            for scene in plan.scenes:
                specs.append(("EXPLICACIÓN", scene.heading, scene.body, scene.visual_kind == "veo"))
            specs.append((
                "SEGURIDAD",
                "Qué hacer con esta información",
                "Úsala para entender mejor tu salud y preparar preguntas. No cambia indicaciones médicas ni sustituye atención profesional.",
                False,
            ))

            duration = min(max(int(target_duration_seconds), 12), 300)
            per_scene = max(3.0, duration / max(len(specs), 1))
            segments: list[Path] = []
            veo_used = False
            for index, (eyebrow, heading, body, wants_veo) in enumerate(specs):
                segment = root / f"segment-{index:02d}.mp4"
                if wants_veo and veo_clip and not veo_used:
                    source = root / "veo-source.mp4"
                    source.write_bytes(veo_clip)
                    self._run([
                        ffmpeg, "-y", "-stream_loop", "-1", "-i", str(source),
                        "-t", f"{per_scene:.2f}",
                        "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,crop={self.width}:{self.height}",
                        "-an", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(segment),
                    ])
                    veo_used = True
                else:
                    slide = root / f"slide-{index:02d}.png"
                    self._slide(slide, eyebrow=eyebrow, heading=heading, body=body, index=index, count=len(specs))
                    self._run([
                        ffmpeg, "-y", "-loop", "1", "-i", str(slide),
                        "-t", f"{per_scene:.2f}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(segment),
                    ])
                segments.append(segment)

            concat = root / "segments.txt"
            concat.write_text("\n".join(f"file '{segment.as_posix()}'" for segment in segments), encoding="utf-8")
            silent_video = root / "visuals.mp4"
            self._run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent_video)])
            output = root / "healthia-explain.mp4"
            self._run([
                ffmpeg, "-y", "-i", str(silent_video), "-i", str(audio_path),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", "-movflags", "+faststart", str(output),
            ])
            data = output.read_bytes()
            if len(data) < 4096 or b"ftyp" not in data[:64]:
                raise RuntimeError("HealthIA Explain renderer produced an invalid MP4")
            return data


class GeneratedEducationMediaStore:
    """Generated education media remains private and patient-scoped."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or ROOT).resolve()

    async def persist(self, *, patient_id: str, video_id: str, content: bytes) -> str:
        bucket_name = os.getenv("HEALTHIA_GCS_BUCKET", "").strip()
        if bucket_name:
            object_name = f"patients/{patient_id}/education/{video_id}.mp4"

            def upload() -> None:
                from google.cloud import storage
                client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
                blob = client.bucket(bucket_name).blob(object_name)
                blob.metadata = {
                    "healthia_patient_id": patient_id,
                    "healthia_video_id": video_id,
                    "healthia_media_kind": "patient_education_video",
                }
                blob.upload_from_string(content, content_type="video/mp4")

            await asyncio.to_thread(upload)
            return f"gs://{bucket_name}/{object_name}"

        allowed = (self.root / ".healthia-one" / "generated_media").resolve()
        path = (allowed / patient_id / f"{video_id}.mp4").resolve()
        if allowed not in path.parents:
            raise PermissionError("Generated media path escaped the patient media root")
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return str(path)


async def load_generated_video(storage_path: str, *, root: Path | None = None) -> bytes | Path:
    value = str(storage_path or "")
    if value.startswith("gs://"):
        parsed = urlparse(value)
        if not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError("Invalid generated video GCS path")

        def download() -> bytes:
            from google.cloud import storage
            client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
            return client.bucket(parsed.netloc).blob(parsed.path.lstrip("/")).download_as_bytes()

        return await asyncio.to_thread(download)

    base = ((root or ROOT).resolve() / ".healthia-one" / "generated_media").resolve()
    path = Path(value).resolve()
    if base not in path.parents or not path.exists() or not path.is_file():
        raise FileNotFoundError(value)
    return path
