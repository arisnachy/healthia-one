from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from healthia_one.education_video_models import EducationFact, EducationVideoPlan, NarrationAudio
from healthia_one.language import normalize_locale


ROOT = Path(__file__).resolve().parents[1]


_VIDEO_COPY: dict[str, dict[str, str]] = {
    "en": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "A visual explanation about {topic}.",
        "your_info": "YOUR INFORMATION", "record_title": "What is recorded in your health record",
        "education": "EXPLANATION", "safety": "SAFETY", "safety_title": "What to do with this information",
        "safety_body": "Use it to understand your health and prepare questions. It does not change medical instructions or replace professional care.",
        "footer": "Clinical education · private",
    },
    "es": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Una explicación visual sobre {topic}.",
        "your_info": "TU INFORMACIÓN", "record_title": "Lo que consta en tu expediente",
        "education": "EXPLICACIÓN", "safety": "SEGURIDAD", "safety_title": "Qué hacer con esta información",
        "safety_body": "Úsala para entender mejor tu salud y preparar preguntas. No cambia indicaciones médicas ni sustituye atención profesional.",
        "footer": "Educación clínica · privado",
    },
    "pt": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Uma explicação visual sobre {topic}.",
        "your_info": "SUAS INFORMAÇÕES", "record_title": "O que está registrado no seu prontuário",
        "education": "EXPLICAÇÃO", "safety": "SEGURANÇA", "safety_title": "O que fazer com estas informações",
        "safety_body": "Use para entender melhor sua saúde e preparar perguntas. Não altera orientações médicas nem substitui cuidados profissionais.",
        "footer": "Educação clínica · privado",
    },
    "fr": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Une explication visuelle sur {topic}.",
        "your_info": "VOS INFORMATIONS", "record_title": "Ce qui est enregistré dans votre dossier",
        "education": "EXPLICATION", "safety": "SÉCURITÉ", "safety_title": "Que faire de ces informations",
        "safety_body": "Utilisez-les pour mieux comprendre votre santé et préparer vos questions. Elles ne modifient pas votre traitement et ne remplacent pas un avis professionnel.",
        "footer": "Éducation clinique · privé",
    },
    "de": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Eine visuelle Erklärung zu {topic}.",
        "your_info": "IHRE INFORMATIONEN", "record_title": "Was in Ihrer Gesundheitsakte dokumentiert ist",
        "education": "ERKLÄRUNG", "safety": "SICHERHEIT", "safety_title": "Was Sie mit diesen Informationen tun können",
        "safety_body": "Nutzen Sie sie, um Ihre Gesundheit besser zu verstehen und Fragen vorzubereiten. Sie ändern keine medizinischen Anweisungen und ersetzen keine professionelle Betreuung.",
        "footer": "Gesundheitsbildung · privat",
    },
    "it": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Una spiegazione visiva su {topic}.",
        "your_info": "LE TUE INFORMAZIONI", "record_title": "Ciò che risulta nella tua cartella clinica",
        "education": "SPIEGAZIONE", "safety": "SICUREZZA", "safety_title": "Cosa fare con queste informazioni",
        "safety_body": "Usale per capire meglio la tua salute e preparare domande. Non modificano le indicazioni mediche e non sostituiscono l'assistenza professionale.",
        "footer": "Educazione clinica · privato",
    },
    "nl": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Een visuele uitleg over {topic}.",
        "your_info": "UW INFORMATIE", "record_title": "Wat in uw gezondheidsdossier staat",
        "education": "UITLEG", "safety": "VEILIGHEID", "safety_title": "Wat u met deze informatie kunt doen",
        "safety_body": "Gebruik dit om uw gezondheid beter te begrijpen en vragen voor te bereiden. Het verandert uw behandeling niet en vervangt geen professionele zorg.",
        "footer": "Gezondheidseducatie · privé",
    },
    "pl": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Wizualne wyjaśnienie: {topic}.",
        "your_info": "TWOJE INFORMACJE", "record_title": "Informacje zapisane w dokumentacji",
        "education": "WYJAŚNIENIE", "safety": "BEZPIECZEŃSTWO", "safety_title": "Co zrobić z tymi informacjami",
        "safety_body": "Wykorzystaj je, aby lepiej zrozumieć swoje zdrowie i przygotować pytania. Nie zmieniają zaleceń i nie zastępują profesjonalnej opieki.",
        "footer": "Edukacja zdrowotna · prywatne",
    },
    "ro": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "O explicație vizuală despre {topic}.",
        "your_info": "INFORMAȚIILE TALE", "record_title": "Ce este înregistrat în dosarul tău",
        "education": "EXPLICAȚIE", "safety": "SIGURANȚĂ", "safety_title": "Ce poți face cu aceste informații",
        "safety_body": "Folosește-le pentru a-ți înțelege mai bine sănătatea și a pregăti întrebări. Nu modifică recomandările medicale și nu înlocuiesc îngrijirea profesională.",
        "footer": "Educație clinică · privat",
    },
    "tr": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "{topic} hakkında görsel bir açıklama.",
        "your_info": "BİLGİLERİNİZ", "record_title": "Sağlık kaydınızda bulunan bilgiler",
        "education": "AÇIKLAMA", "safety": "GÜVENLİK", "safety_title": "Bu bilgilerle ne yapabilirsiniz",
        "safety_body": "Sağlığınızı daha iyi anlamak ve sorular hazırlamak için kullanın. Tıbbi talimatları değiştirmez ve profesyonel bakımın yerini tutmaz.",
        "footer": "Sağlık eğitimi · özel",
    },
    "id": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Penjelasan visual tentang {topic}.",
        "your_info": "INFORMASI ANDA", "record_title": "Yang tercatat dalam rekam kesehatan Anda",
        "education": "PENJELASAN", "safety": "KEAMANAN", "safety_title": "Apa yang dapat dilakukan dengan informasi ini",
        "safety_body": "Gunakan untuk memahami kesehatan Anda dan menyiapkan pertanyaan. Informasi ini tidak mengubah instruksi medis dan tidak menggantikan perawatan profesional.",
        "footer": "Edukasi klinis · pribadi",
    },
    "vi": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Giải thích trực quan về {topic}.",
        "your_info": "THÔNG TIN CỦA BẠN", "record_title": "Thông tin đã được ghi trong hồ sơ sức khỏe",
        "education": "GIẢI THÍCH", "safety": "AN TOÀN", "safety_title": "Bạn nên làm gì với thông tin này",
        "safety_body": "Hãy dùng để hiểu sức khỏe tốt hơn và chuẩn bị câu hỏi. Nội dung này không thay đổi chỉ định y tế và không thay thế chăm sóc chuyên môn.",
        "footer": "Giáo dục sức khỏe · riêng tư",
    },
    "ru": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Наглядное объяснение: {topic}.",
        "your_info": "ВАША ИНФОРМАЦИЯ", "record_title": "Что записано в вашей медицинской карте",
        "education": "ОБЪЯСНЕНИЕ", "safety": "БЕЗОПАСНОСТЬ", "safety_title": "Как использовать эту информацию",
        "safety_body": "Используйте её, чтобы лучше понимать своё здоровье и подготовить вопросы. Она не меняет назначения и не заменяет профессиональную помощь.",
        "footer": "Медицинское обучение · приватно",
    },
    "uk": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "Наочне пояснення: {topic}.",
        "your_info": "ВАША ІНФОРМАЦІЯ", "record_title": "Що записано у вашій медичній картці",
        "education": "ПОЯСНЕННЯ", "safety": "БЕЗПЕКА", "safety_title": "Як використати цю інформацію",
        "safety_body": "Використовуйте її, щоб краще розуміти своє здоров’я та підготувати запитання. Вона не змінює призначень і не замінює професійну допомогу.",
        "footer": "Медична освіта · приватно",
    },
    "ar": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "شرح مرئي حول {topic}.",
        "your_info": "معلوماتك", "record_title": "ما هو مسجل في ملفك الصحي",
        "education": "الشرح", "safety": "السلامة", "safety_title": "ماذا تفعل بهذه المعلومات",
        "safety_body": "استخدمها لفهم صحتك بشكل أفضل وتحضير أسئلتك. لا تغيّر التعليمات الطبية ولا تحل محل الرعاية المتخصصة.",
        "footer": "تثقيف صحي · خاص",
    },
    "hi": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "{topic} के बारे में दृश्य व्याख्या।",
        "your_info": "आपकी जानकारी", "record_title": "आपके स्वास्थ्य रिकॉर्ड में दर्ज जानकारी",
        "education": "व्याख्या", "safety": "सुरक्षा", "safety_title": "इस जानकारी का उपयोग कैसे करें",
        "safety_body": "इसे अपनी सेहत बेहतर समझने और सवाल तैयार करने के लिए उपयोग करें। यह चिकित्सा निर्देश नहीं बदलता और पेशेवर देखभाल का स्थान नहीं लेता।",
        "footer": "स्वास्थ्य शिक्षा · निजी",
    },
    "ja": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "{topic}についての視覚的な説明です。",
        "your_info": "あなたの情報", "record_title": "健康記録に登録されている内容",
        "education": "説明", "safety": "安全性", "safety_title": "この情報の活用方法",
        "safety_body": "健康を理解し質問を準備するために使用してください。医療上の指示を変更したり、専門的な医療の代わりになるものではありません。",
        "footer": "健康教育 · 非公開",
    },
    "ko": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "{topic}에 대한 시각적 설명입니다.",
        "your_info": "내 정보", "record_title": "건강 기록에 저장된 정보",
        "education": "설명", "safety": "안전", "safety_title": "이 정보를 활용하는 방법",
        "safety_body": "건강을 더 잘 이해하고 질문을 준비하는 데 사용하세요. 의료 지시를 변경하거나 전문 치료를 대신하지 않습니다.",
        "footer": "건강 교육 · 비공개",
    },
    "zh": {
        "explain": "HEALTHIA EXPLAIN", "visual_about": "关于{topic}的可视化说明。",
        "your_info": "您的信息", "record_title": "健康记录中已保存的信息",
        "education": "说明", "safety": "安全", "safety_title": "如何使用这些信息",
        "safety_body": "请用它来更好地了解自己的健康并准备问题。它不会改变医疗指示，也不能替代专业医疗服务。",
        "footer": "健康教育 · 私密",
    },
}


def video_copy(locale: str) -> dict[str, str]:
    return _VIDEO_COPY.get(normalize_locale(locale), _VIDEO_COPY["en"])


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
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

    def _slide(self, path: Path, *, eyebrow: str, heading: str, body: str, index: int, count: int, footer: str) -> None:
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
        draw.text((820, 643), footer[:36], font=_font(17), fill=(105, 121, 145))
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
        locale: str = "es",
    ) -> bytes:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        copy = video_copy(locale)
        with tempfile.TemporaryDirectory(prefix="healthia-explain-") as tmp:
            root = Path(tmp)
            audio_path = root / f"narration{narration.suffix}"
            audio_path.write_bytes(narration.data)

            specs: list[tuple[str, str, str, bool]] = [
                (copy["explain"], title, copy["visual_about"].format(topic=topic), False)
            ]
            if facts:
                fact_body = "  •  ".join(f"{item.label}: {item.value}" for item in facts[:4])
                specs.append((copy["your_info"], copy["record_title"], fact_body, False))
            for scene in plan.scenes:
                specs.append((copy["education"], scene.heading, scene.body, scene.visual_kind == "veo"))
            specs.append((copy["safety"], copy["safety_title"], copy["safety_body"], False))

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
                    self._slide(
                        slide, eyebrow=eyebrow, heading=heading, body=body,
                        index=index, count=len(specs), footer=copy["footer"],
                    )
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
