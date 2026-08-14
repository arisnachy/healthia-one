from __future__ import annotations

import asyncio
import io
import json
import re
import wave
from typing import Any, Awaitable, Callable, Protocol

from healthia_one.control import audit
from healthia_one.education_video_google import GoogleEducationMediaProvider
from healthia_one.education_video_models import (
    EducationFact,
    EducationVideoPlan,
    NarrationAudio,
    collect_topic_facts,
    compose_narration,
    is_acceptance,
    is_explanation_request,
    is_rejection,
    is_video_request,
    latest_offer,
    normalize,
    requested_duration_seconds,
    topic_from_text,
    validate_plan,
)
from healthia_one.education_video_renderer import EducationVideoRenderer, GeneratedEducationMediaStore
from healthia_one.language import LANGUAGE_NAMES, current_requested_locale, normalize_locale, resolve_response_locale
from healthia_one.models import ChatMessage, ChatResponse, HealthMission, MissionStatus, PatientState, RiskLevel, new_id
from healthia_one.safety import assess_text


class EducationMediaProvider(Protocol):
    async def synthesize(self, *, patient_id: str, mission_id: str, text: str, locale: str) -> NarrationAudio: ...
    async def maybe_generate_veo_clip(self, *, patient_id: str, mission_id: str, generic_prompt: str) -> tuple[bytes | None, str]: ...


Planner = Callable[[PatientState, str, str, int, list[EducationFact]], Awaitable[EducationVideoPlan]]


_COPY: dict[str, dict[str, str]] = {
    "en": {
        "topic": "this topic", "offer": "If it helps, I can prepare a short private video explaining **{topic}**. Want me to create it?",
        "declined": "No problem, we can keep it here.", "need_topic": "Tell me what condition, result, or health topic you want the video to explain.",
        "mission": "Explain {topic} in a video", "next": "Create an evidence-grounded script and render the private video",
        "retry": "Retry generation when the media runtime is available", "failed": "I couldn't complete the video in this run, so I won't show you a fake or incomplete file. The request remains saved and can be retried.",
        "done_next": "Watch the video and note any questions for the next conversation or visit", "done": "Done. I prepared **{title}**.",
        "watch": "Watch video", "separation": "Your recorded information is separated from general education; the video does not change your treatment.", "create": "Create video",
    },
    "es": {
        "topic": "este tema", "offer": "Si te ayuda, puedo prepararte un video corto y privado explicando **{topic}**. ¿Quieres que lo cree?",
        "declined": "Perfecto, seguimos por aquí.", "need_topic": "Dime qué patología, resultado o tema de salud quieres que explique en el video.",
        "mission": "Explicar {topic} en video", "next": "Crear un guion basado en evidencia y renderizar el video privado",
        "retry": "Reintentar la generación cuando el runtime de medios esté disponible", "failed": "No pude completar el video en esta ejecución, así que no voy a mostrarte un archivo falso o incompleto. La solicitud quedó guardada y se puede reintentar.",
        "done_next": "Ver el video y anotar dudas para la próxima conversación o consulta", "done": "Listo. Preparé **{title}**.",
        "watch": "Ver video", "separation": "Tus datos aparecen separados de la explicación general; el video no cambia tu tratamiento.", "create": "Crear video",
    },
    "pt": {
        "topic": "este tema", "offer": "Se ajudar, posso preparar um vídeo curto e privado explicando **{topic}**. Quer que eu crie?",
        "declined": "Tudo bem, podemos continuar por aqui.", "need_topic": "Diga qual condição, resultado ou tema de saúde você quer que o vídeo explique.",
        "mission": "Explicar {topic} em vídeo", "next": "Criar um roteiro baseado em evidências e renderizar o vídeo privado",
        "retry": "Tentar novamente quando o sistema de mídia estiver disponível", "failed": "Não consegui concluir o vídeo nesta execução, então não vou mostrar um arquivo falso ou incompleto. O pedido ficou salvo e pode ser tentado novamente.",
        "done_next": "Assistir ao vídeo e anotar dúvidas para a próxima conversa ou consulta", "done": "Pronto. Preparei **{title}**.",
        "watch": "Assistir ao vídeo", "separation": "Seus dados registrados ficam separados da explicação geral; o vídeo não altera seu tratamento.", "create": "Criar vídeo",
    },
    "fr": {
        "topic": "ce sujet", "offer": "Si cela vous aide, je peux préparer une courte vidéo privée pour expliquer **{topic}**. Voulez-vous que je la crée ?",
        "declined": "Pas de problème, nous pouvons continuer ici.", "need_topic": "Dites-moi quelle maladie, quel résultat ou quel sujet de santé vous voulez voir expliqué en vidéo.",
        "mission": "Expliquer {topic} en vidéo", "next": "Créer un script fondé sur les preuves et produire la vidéo privée",
        "retry": "Réessayer lorsque le service multimédia sera disponible", "failed": "Je n’ai pas pu terminer la vidéo cette fois-ci, donc je ne vous montrerai pas un fichier faux ou incomplet. La demande est enregistrée et pourra être relancée.",
        "done_next": "Regarder la vidéo et noter vos questions pour la prochaine conversation ou consultation", "done": "C’est prêt. J’ai préparé **{title}**.",
        "watch": "Voir la vidéo", "separation": "Vos données enregistrées sont séparées de l’explication générale ; la vidéo ne modifie pas votre traitement.", "create": "Créer la vidéo",
    },
    "de": {
        "topic": "dieses Thema", "offer": "Wenn es hilft, kann ich ein kurzes privates Video zu **{topic}** erstellen. Soll ich es erstellen?",
        "declined": "Kein Problem, wir können hier weitermachen.", "need_topic": "Sagen Sie mir, welche Erkrankung, welches Ergebnis oder welches Gesundheitsthema das Video erklären soll.",
        "mission": "{topic} in einem Video erklären", "next": "Ein evidenzbasiertes Skript erstellen und das private Video rendern",
        "retry": "Erneut versuchen, wenn die Medienverarbeitung verfügbar ist", "failed": "Ich konnte das Video in diesem Durchlauf nicht fertigstellen. Deshalb zeige ich keine falsche oder unvollständige Datei. Die Anfrage bleibt gespeichert und kann erneut versucht werden.",
        "done_next": "Video ansehen und Fragen für das nächste Gespräch oder den nächsten Termin notieren", "done": "Fertig. Ich habe **{title}** vorbereitet.",
        "watch": "Video ansehen", "separation": "Ihre dokumentierten Daten sind von der allgemeinen Erklärung getrennt; das Video ändert Ihre Behandlung nicht.", "create": "Video erstellen",
    },
    "it": {
        "topic": "questo argomento", "offer": "Se può aiutarti, posso preparare un breve video privato che spiega **{topic}**. Vuoi che lo crei?",
        "declined": "Va bene, possiamo continuare qui.", "need_topic": "Dimmi quale patologia, risultato o argomento di salute vuoi che il video spieghi.",
        "mission": "Spiegare {topic} in un video", "next": "Creare uno script basato sulle evidenze e produrre il video privato",
        "retry": "Riprovare quando il sistema multimediale sarà disponibile", "failed": "Non sono riuscito a completare il video in questa esecuzione, quindi non mostrerò un file falso o incompleto. La richiesta resta salvata e può essere riprovata.",
        "done_next": "Guardare il video e annotare le domande per la prossima conversazione o visita", "done": "Fatto. Ho preparato **{title}**.",
        "watch": "Guarda il video", "separation": "I tuoi dati registrati sono separati dalla spiegazione generale; il video non modifica il trattamento.", "create": "Crea video",
    },
    "nl": {"topic":"dit onderwerp","offer":"Als het helpt, kan ik een korte privévideo maken over **{topic}**. Zal ik die maken?","declined":"Geen probleem, we kunnen hier verdergaan.","need_topic":"Vertel welke aandoening, uitslag of gezondheidsonderwerp je in de video wilt laten uitleggen.","mission":"{topic} in een video uitleggen","next":"Een evidence-based script maken en de privévideo renderen","retry":"Opnieuw proberen wanneer de mediaruntime beschikbaar is","failed":"Ik kon de video deze keer niet voltooien, dus ik laat geen nep- of onvolledig bestand zien. De aanvraag blijft opgeslagen en kan opnieuw worden geprobeerd.","done_next":"Bekijk de video en noteer vragen voor het volgende gesprek of bezoek","done":"Klaar. Ik heb **{title}** voorbereid.","watch":"Video bekijken","separation":"Je geregistreerde gegevens staan los van de algemene uitleg; de video verandert je behandeling niet.","create":"Video maken"},
    "pl": {"topic":"ten temat","offer":"Jeśli to pomoże, mogę przygotować krótki prywatny film wyjaśniający **{topic}**. Mam go utworzyć?","declined":"W porządku, możemy kontynuować tutaj.","need_topic":"Powiedz, jaką chorobę, wynik lub temat zdrowotny ma wyjaśnić film.","mission":"Wyjaśnić {topic} w filmie","next":"Utworzyć skrypt oparty na dowodach i wyrenderować prywatny film","retry":"Spróbować ponownie, gdy moduł multimediów będzie dostępny","failed":"Nie udało mi się ukończyć filmu w tej próbie, więc nie pokażę fałszywego ani niepełnego pliku. Prośba została zapisana i można spróbować ponownie.","done_next":"Obejrzeć film i zapisać pytania na następną rozmowę lub wizytę","done":"Gotowe. Przygotowałem **{title}**.","watch":"Obejrzyj film","separation":"Twoje zapisane dane są oddzielone od ogólnego wyjaśnienia; film nie zmienia leczenia.","create":"Utwórz film"},
    "ro": {"topic":"acest subiect","offer":"Dacă te ajută, pot pregăti un videoclip privat scurt care explică **{topic}**. Vrei să-l creez?","declined":"Nicio problemă, putem continua aici.","need_topic":"Spune-mi ce afecțiune, rezultat sau subiect de sănătate vrei să fie explicat în videoclip.","mission":"Explică {topic} într-un videoclip","next":"Creează un scenariu bazat pe dovezi și redă videoclipul privat","retry":"Încearcă din nou când sistemul media este disponibil","failed":"Nu am putut finaliza videoclipul în această rulare, așa că nu îți voi arăta un fișier fals sau incomplet. Cererea a rămas salvată și poate fi reluată.","done_next":"Urmărește videoclipul și notează întrebările pentru următoarea conversație sau consultație","done":"Gata. Am pregătit **{title}**.","watch":"Vezi videoclipul","separation":"Datele tale înregistrate sunt separate de explicația generală; videoclipul nu îți schimbă tratamentul.","create":"Creează videoclip"},
    "ru": {"topic":"эту тему","offer":"Если это поможет, я могу подготовить короткое приватное видео с объяснением **{topic}**. Создать его?","declined":"Хорошо, можем продолжить здесь.","need_topic":"Скажите, какое заболевание, результат или тему о здоровье вы хотите объяснить в видео.","mission":"Объяснить {topic} в видео","next":"Создать сценарий на основе данных и подготовить приватное видео","retry":"Повторить создание, когда медиасистема будет доступна","failed":"В этот раз я не смог завершить видео, поэтому не буду показывать ложный или неполный файл. Запрос сохранён, и его можно повторить.","done_next":"Посмотреть видео и записать вопросы для следующего разговора или визита","done":"Готово. Я подготовил **{title}**.","watch":"Смотреть видео","separation":"Ваши записанные данные отделены от общего объяснения; видео не меняет ваше лечение.","create":"Создать видео"},
    "uk": {"topic":"цю тему","offer":"Якщо це допоможе, я можу підготувати коротке приватне відео з поясненням **{topic}**. Створити його?","declined":"Добре, можемо продовжити тут.","need_topic":"Скажіть, який стан, результат або тему здоров’я ви хочете пояснити у відео.","mission":"Пояснити {topic} у відео","next":"Створити сценарій на основі доказів і підготувати приватне відео","retry":"Повторити створення, коли медіасистема буде доступна","failed":"Цього разу я не зміг завершити відео, тому не показуватиму фальшивий або неповний файл. Запит збережено і його можна повторити.","done_next":"Переглянути відео й записати запитання для наступної розмови або візиту","done":"Готово. Я підготував **{title}**.","watch":"Переглянути відео","separation":"Ваші записані дані відокремлені від загального пояснення; відео не змінює лікування.","create":"Створити відео"},
    "tr": {"topic":"bu konu","offer":"Yardımcı olacaksa **{topic}** hakkında kısa ve özel bir video hazırlayabilirim. Oluşturmamı ister misiniz?","declined":"Sorun değil, buradan devam edebiliriz.","need_topic":"Videoda hangi hastalık, sonuç veya sağlık konusunun açıklanmasını istediğinizi söyleyin.","mission":"{topic} konusunu videoda açıkla","next":"Kanıta dayalı bir senaryo oluştur ve özel videoyu hazırla","retry":"Medya sistemi kullanılabilir olduğunda yeniden dene","failed":"Bu çalışmada videoyu tamamlayamadım; bu nedenle sahte veya eksik bir dosya göstermeyeceğim. İstek kaydedildi ve yeniden denenebilir.","done_next":"Videoyu izle ve sonraki görüşme veya ziyaret için sorularını not et","done":"Hazır. **{title}** videosunu hazırladım.","watch":"Videoyu izle","separation":"Kayıtlı bilgileriniz genel açıklamadan ayrı tutulur; video tedavinizi değiştirmez.","create":"Video oluştur"},
    "id": {"topic":"topik ini","offer":"Jika membantu, saya dapat menyiapkan video pribadi singkat yang menjelaskan **{topic}**. Mau saya buat?","declined":"Tidak masalah, kita bisa lanjut di sini.","need_topic":"Beri tahu kondisi, hasil, atau topik kesehatan apa yang ingin dijelaskan dalam video.","mission":"Jelaskan {topic} dalam video","next":"Buat naskah berbasis bukti dan render video pribadi","retry":"Coba lagi saat sistem media tersedia","failed":"Saya tidak dapat menyelesaikan video pada proses ini, jadi saya tidak akan menampilkan file palsu atau tidak lengkap. Permintaan tetap tersimpan dan dapat dicoba lagi.","done_next":"Tonton video dan catat pertanyaan untuk percakapan atau kunjungan berikutnya","done":"Selesai. Saya menyiapkan **{title}**.","watch":"Tonton video","separation":"Informasi Anda yang tercatat dipisahkan dari edukasi umum; video tidak mengubah pengobatan Anda.","create":"Buat video"},
    "vi": {"topic":"chủ đề này","offer":"Nếu hữu ích, tôi có thể chuẩn bị một video riêng tư ngắn giải thích **{topic}**. Bạn có muốn tôi tạo không?","declined":"Không sao, chúng ta có thể tiếp tục ở đây.","need_topic":"Hãy cho tôi biết bệnh lý, kết quả hoặc chủ đề sức khỏe nào bạn muốn video giải thích.","mission":"Giải thích {topic} bằng video","next":"Tạo kịch bản dựa trên bằng chứng và dựng video riêng tư","retry":"Thử lại khi hệ thống phương tiện khả dụng","failed":"Tôi không thể hoàn thành video trong lần này, vì vậy tôi sẽ không hiển thị tệp giả hoặc chưa hoàn chỉnh. Yêu cầu vẫn được lưu và có thể thử lại.","done_next":"Xem video và ghi lại câu hỏi cho cuộc trò chuyện hoặc lần khám tiếp theo","done":"Xong. Tôi đã chuẩn bị **{title}**.","watch":"Xem video","separation":"Thông tin đã ghi nhận của bạn được tách khỏi phần giáo dục chung; video không thay đổi điều trị.","create":"Tạo video"},
    "ar": {"topic":"هذا الموضوع","offer":"إذا كان ذلك مفيدًا، يمكنني إعداد فيديو خاص قصير يشرح **{topic}**. هل تريد أن أنشئه؟","declined":"لا مشكلة، يمكننا المتابعة هنا.","need_topic":"أخبرني ما الحالة أو النتيجة أو الموضوع الصحي الذي تريد أن يشرحه الفيديو.","mission":"شرح {topic} في فيديو","next":"إنشاء نص مبني على الأدلة وإنتاج الفيديو الخاص","retry":"إعادة المحاولة عندما تصبح خدمة الوسائط متاحة","failed":"لم أتمكن من إكمال الفيديو هذه المرة، لذلك لن أعرض ملفًا مزيفًا أو غير مكتمل. تم حفظ الطلب ويمكن إعادة المحاولة.","done_next":"شاهد الفيديو وسجّل أسئلتك للمحادثة أو الزيارة التالية","done":"تم. أعددت **{title}**.","watch":"مشاهدة الفيديو","separation":"تظل معلوماتك المسجلة منفصلة عن الشرح العام؛ الفيديو لا يغيّر علاجك.","create":"إنشاء فيديو"},
    "hi": {"topic":"यह विषय","offer":"अगर यह मददगार हो, तो मैं **{topic}** समझाने वाला एक छोटा निजी वीडियो बना सकता हूँ। क्या मैं इसे बनाऊँ?","declined":"ठीक है, हम यहीं जारी रख सकते हैं।","need_topic":"बताइए कि किस बीमारी, परिणाम या स्वास्थ्य विषय को आप वीडियो में समझाना चाहते हैं।","mission":"वीडियो में {topic} समझाएँ","next":"साक्ष्य-आधारित स्क्रिप्ट बनाकर निजी वीडियो तैयार करें","retry":"मीडिया सिस्टम उपलब्ध होने पर फिर कोशिश करें","failed":"इस बार मैं वीडियो पूरा नहीं कर पाया, इसलिए मैं नकली या अधूरी फ़ाइल नहीं दिखाऊँगा। अनुरोध सुरक्षित है और दोबारा प्रयास किया जा सकता है।","done_next":"वीडियो देखें और अगली बातचीत या मुलाक़ात के लिए प्रश्न लिख लें","done":"तैयार है। मैंने **{title}** बनाया है।","watch":"वीडियो देखें","separation":"आपकी दर्ज जानकारी सामान्य शिक्षा से अलग रखी जाती है; वीडियो आपके उपचार को नहीं बदलता।","create":"वीडियो बनाएँ"},
    "ja": {"topic":"このテーマ","offer":"必要であれば、**{topic}**を説明する短いプライベート動画を作れます。作成しますか？","declined":"わかりました。ここで続けましょう。","need_topic":"動画で説明してほしい病気、検査結果、または健康テーマを教えてください。","mission":"{topic}を動画で説明","next":"根拠に基づく台本を作り、プライベート動画を生成する","retry":"メディア機能が利用可能になったら再試行する","failed":"今回は動画を完成できなかったため、偽のファイルや不完全なファイルは表示しません。リクエストは保存されており、再試行できます。","done_next":"動画を見て、次の会話や受診で聞きたいことをメモする","done":"できました。**{title}**を用意しました。","watch":"動画を見る","separation":"記録された情報は一般的な説明と分けて表示され、動画が治療内容を変更することはありません。","create":"動画を作成"},
    "ko": {"topic":"이 주제","offer":"도움이 된다면 **{topic}**을 설명하는 짧은 비공개 영상을 만들어 드릴 수 있어요. 만들까요?","declined":"괜찮습니다. 여기서 계속할 수 있어요.","need_topic":"영상에서 설명해 드릴 질환, 검사 결과 또는 건강 주제를 알려 주세요.","mission":"영상으로 {topic} 설명하기","next":"근거 기반 대본을 만들고 비공개 영상을 생성하기","retry":"미디어 시스템을 사용할 수 있을 때 다시 시도하기","failed":"이번에는 영상을 완료하지 못했기 때문에 가짜이거나 불완전한 파일을 보여드리지 않겠습니다. 요청은 저장되어 있으며 다시 시도할 수 있습니다.","done_next":"영상을 보고 다음 대화나 진료에서 물어볼 질문을 메모하기","done":"완료했습니다. **{title}**을 준비했어요.","watch":"영상 보기","separation":"기록된 정보는 일반 교육 내용과 분리되며, 영상은 치료를 변경하지 않습니다.","create":"영상 만들기"},
    "zh": {"topic":"这个主题","offer":"如果有帮助，我可以制作一个简短的私密视频来解释 **{topic}**。要我制作吗？","declined":"没问题，我们可以继续在这里聊。","need_topic":"请告诉我你希望视频解释哪种疾病、检查结果或健康主题。","mission":"用视频解释{topic}","next":"根据证据生成脚本并制作私密视频","retry":"媒体系统可用时重新尝试","failed":"这次我没能完成视频，因此不会向你显示虚假或不完整的文件。请求已保存，可以稍后重试。","done_next":"观看视频，并记录下次对话或就诊时要问的问题","done":"完成了。我准备了 **{title}**。","watch":"观看视频","separation":"你的已记录信息与一般健康教育内容分开呈现；视频不会改变你的治疗方案。","create":"制作视频"},
}


def _copy(locale: str, key: str, **values: str) -> str:
    language = normalize_locale(locale)
    template = _COPY.get(language, _COPY["en"])[key]
    return template.format(**values)


def _education_system_instruction(locale: str) -> str:
    language = LANGUAGE_NAMES.get(normalize_locale(locale), "English")
    return f"""
You are the clinical education director inside HealthIA ONE.
Create a patient-facing educational video plan entirely in {language}. Return JSON only.

Safety and truth rules:
- Do not diagnose a new disease, prescribe, change doses, tell the patient to stop medication, or claim certainty not present in the allowed facts.
- The only patient-specific information you may use is in allowed_patient_facts.
- Keep patient-specific facts separate from general medical education.
- Do not copy patient-specific values into Veo prompts.
- Veo prompts must be generic medical education imagery: no names, ages, locations, dates, medication names, laboratory values, measurements, identifiers, text overlays, or PHI.
- The veo_prompt itself must be written in English for predictable visual generation, even though every patient-visible field is in {language}.
- NEVER use digits or numeric tokens in veo_prompt, including labels such as 3D; spell generic visual concepts with words instead.
- Prefer controlled cards for exact values, medication names, numbers, warning signs, and clinical labels.
- Use at most ONE scene with visual_kind="veo"; all other scenes are controlled cards. For a physiological topic where motion materially improves understanding (for example blood flow, breathing, digestion, joint motion, or cardiac function), use exactly ONE generic Veo scene.
- Do not use a talking doctor avatar or person generation.
- Keep narration within the requested duration.

JSON shape:
{{
  "title": "...",
  "summary": "...",
  "patient_fact_keys": ["only keys from allowed_patient_facts that truly help"],
  "scenes": [
    {{"heading":"...","body":"...","narration":"...","visual_kind":"card|veo","veo_prompt":"generic English prompt only for veo"}}
  ]
}}
""".strip()


def _json_object(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Gemini did not return a JSON education video plan")
    return json.loads(text[start : end + 1])


def _silent_narration(seconds: int) -> NarrationAudio:
    """Safe visual-only fallback when private TTS is unavailable."""
    sample_rate = 8000
    frames = b"\x00\x00" * sample_rate * min(max(seconds, 12), 300)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return NarrationAudio(data=buffer.getvalue(), suffix=".wav", mime_type="audio/wav")


class PatientEducationVideoRouter:
    """Chat-first HealthIA Explain mission: explain -> offer -> consent -> private video."""

    def __init__(
        self,
        settings,
        *,
        client_provider: Callable[[], Any] | None = None,
        cost_guard: Any | None = None,
        planner: Planner | None = None,
        media_provider: EducationMediaProvider | None = None,
        renderer: EducationVideoRenderer | None = None,
        media_store: GeneratedEducationMediaStore | None = None,
    ) -> None:
        self.settings = settings
        self.client_provider = client_provider
        self.cost_guard = cost_guard
        self._planner = planner
        self.media_provider = media_provider or GoogleEducationMediaProvider(settings)
        self.renderer = renderer or EducationVideoRenderer()
        self.media_store = media_store or GeneratedEducationMediaStore()

    def _response_locale(self, state: PatientState, patient_text: str, response: ChatResponse | None = None) -> str:
        if response is not None:
            metadata_locale = str((response.message.metadata or {}).get("response_locale") or "").strip()
            if metadata_locale:
                return normalize_locale(metadata_locale)
        return resolve_response_locale(
            patient_text,
            requested_locale=current_requested_locale(),
            profile_locale=state.profile.locale,
        )

    async def _gemini_plan(
        self,
        state: PatientState,
        topic: str,
        locale: str,
        duration_seconds: int,
        facts: list[EducationFact],
    ) -> EducationVideoPlan:
        if self.client_provider is None or self.cost_guard is None:
            raise RuntimeError("HealthIA Explain Gemini planner is not configured")
        if getattr(self.settings, "llm_backend", "mock") != "gemini_api" or not getattr(self.settings, "adk_ready", False):
            raise RuntimeError("Gemini is not configured for HealthIA Explain")
        self.cost_guard.authorize("patient_education_video_plan")
        payload = {
            "task": "build_evidence_grounded_patient_education_video",
            "topic": topic,
            "response_locale": locale,
            "requested_duration_seconds": duration_seconds,
            "target_total_narration_words": min(max(int(duration_seconds * 2.0), 90), 650),
            "allowed_patient_facts": [item.model_dump(mode="json") for item in facts],
            "rules": {
                "patient_specific_values_only_from_allowed_facts": True,
                "veo_must_be_generic_and_phi_free": True,
                "max_veo_scenes": 1,
                "exact_values_belong_on_controlled_cards": True,
            },
        }
        interaction = self.client_provider().interactions.create(
            model=self.settings.model,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            system_instruction=_education_system_instruction(locale),
            generation_config={
                "max_output_tokens": min(int(self.cost_guard.max_output_tokens), 1400),
                "thinking_level": "minimal",
                "response_mime_type": "application/json",
            },
            store=False,
        )
        return EducationVideoPlan.model_validate(_json_object(str(getattr(interaction, "output_text", "") or "")))

    async def _plan(self, state: PatientState, topic: str, locale: str, duration_seconds: int, facts: list[EducationFact]) -> EducationVideoPlan:
        planner = self._planner or self._gemini_plan
        plan = await planner(state, topic, locale, duration_seconds, facts)
        return validate_plan(plan, facts, state.profile.display_name)

    def maybe_attach_offer(self, state: PatientState, patient_text: str, response: ChatResponse) -> ChatResponse:
        if is_video_request(patient_text) or not is_explanation_request(patient_text):
            return response
        if response.message.risk_level == RiskLevel.URGENT:
            return response
        interview = (response.message.metadata or {}).get("clinical_interview")
        if isinstance(interview, dict) and interview.get("status") in {"awaiting_answers", "ready_for_synthesis"}:
            return response
        locale = self._response_locale(state, patient_text, response)
        topic = topic_from_text(patient_text) or _copy(locale, "topic")
        offer = {"topic": topic, "duration_seconds": 90, "locale": locale, "requires_confirmation": True}
        response.message.metadata["education_video_offer"] = offer
        response.message.metadata["ui_action"] = {
            "type": "offer_education_video",
            "topic": topic,
            "label": _copy(locale, "create"),
            "locale": locale,
            "label_es": _copy("es", "create"),
            "label_en": _copy("en", "create"),
        }
        sentence = _copy(locale, "offer", topic=topic)
        if sentence not in response.message.content:
            response.message.content = f"{response.message.content.rstrip()}\n\n{sentence}"
        return response

    async def respond(self, state: PatientState, patient_text: str) -> ChatResponse | None:
        if assess_text(patient_text).must_stop_normal_flow:
            return None
        offer = latest_offer(state)
        accepted_offer = bool(offer and is_acceptance(patient_text))
        if offer and is_rejection(patient_text):
            locale = normalize_locale(str(offer.get("locale") or self._response_locale(state, patient_text)))
            return ChatResponse(message=ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA",
                content=_copy(locale, "declined"),
                metadata={"education_video_offer_declined": True, "response_locale": locale},
            ))
        if not is_video_request(patient_text) and not accepted_offer:
            return None

        locale = normalize_locale(str(offer.get("locale") or "")) if accepted_offer and offer else self._response_locale(state, patient_text)
        topic = str(offer.get("topic") or "") if accepted_offer and offer else topic_from_text(patient_text)
        duration_seconds = int(offer.get("duration_seconds") or 90) if accepted_offer and offer else requested_duration_seconds(patient_text)
        if not topic or normalize(topic) in {"eso", "esto", "that", "this", "it", "isso", "isto", "cela", "das", "questo"}:
            return ChatResponse(message=ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA",
                content=_copy(locale, "need_topic"),
                metadata={"education_video_needs_topic": True, "response_locale": locale},
            ))

        facts = collect_topic_facts(state, topic, locale)
        mission = HealthMission(
            patient_id=state.profile.id,
            title=_copy(locale, "mission", topic=topic),
            mission_type="patient_education_video",
            status=MissionStatus.ACTIVE,
            risk_level=RiskLevel.INFO,
            next_action=_copy(locale, "next"),
            evidence_ids=[item.source_id for item in facts],
        )
        state.missions.append(mission)
        audit(
            state,
            actor="patient",
            action="authorize_patient_education_video",
            resource_type="health_mission",
            resource_id=mission.id,
            details={
                "topic": topic,
                "locale": locale,
                "duration_seconds": duration_seconds,
                "consent_source": "accepted_offer" if accepted_offer else "direct_patient_request",
                "patient_fact_count": len(facts),
                "veo_optional": True,
            },
        )

        try:
            plan = await self._plan(state, topic, locale, duration_seconds, facts)
            narration_text = compose_narration(plan, facts, locale)
            narration_status = "gemini_tts"
            try:
                narration = await self.media_provider.synthesize(
                    patient_id=state.profile.id,
                    mission_id=mission.id,
                    text=narration_text,
                    locale=locale,
                )
            except Exception:
                narration = _silent_narration(duration_seconds)
                narration_status = "visual_only_fallback"

            veo_scene = next((scene for scene in plan.scenes if scene.visual_kind == "veo"), None)
            veo_clip: bytes | None = None
            veo_operation = ""
            if veo_scene is not None:
                try:
                    veo_clip, veo_operation = await self.media_provider.maybe_generate_veo_clip(
                        patient_id=state.profile.id,
                        mission_id=mission.id,
                        generic_prompt=veo_scene.veo_prompt,
                    )
                except Exception:
                    veo_clip, veo_operation = None, ""

            selected_keys = set(plan.patient_fact_keys)
            media_bytes = await asyncio.to_thread(
                self.renderer.render,
                title=plan.title,
                topic=topic,
                facts=[fact for fact in facts if fact.key in selected_keys],
                plan=plan,
                narration=narration,
                target_duration_seconds=duration_seconds,
                veo_clip=veo_clip,
                locale=locale,
            )
            video_id = new_id("video")
            storage_path = await self.media_store.persist(
                patient_id=state.profile.id,
                video_id=video_id,
                content=media_bytes,
            )
            public_path = f"/api/education/videos/{video_id}"
        except Exception as exc:
            mission.next_action = _copy(locale, "retry")
            audit(
                state,
                actor="healthia",
                action="generate_patient_education_video",
                resource_type="health_mission",
                resource_id=mission.id,
                outcome="failed",
                details={"error_type": type(exc).__name__, "locale": locale, "no_fake_video": True},
            )
            return ChatResponse(
                message=ChatMessage(
                    patient_id=state.profile.id,
                    role="assistant",
                    author="HealthIA",
                    content=_copy(locale, "failed"),
                    mission_id=mission.id,
                    metadata={
                        "response_locale": locale,
                        "education_video": {
                            "status": "generation_failed",
                            "topic": topic,
                            "locale": locale,
                            "private": True,
                            "error_type": type(exc).__name__,
                        },
                    },
                ),
                mission=mission,
            )

        mission.status = MissionStatus.COMPLETED
        mission.next_action = _copy(locale, "done_next")
        mission.closure_evidence.extend([f"education_video:{video_id}", *[f"source:{item.source_id}" for item in facts]])
        audit(
            state,
            actor="healthia",
            action="generate_patient_education_video",
            resource_type="health_mission",
            resource_id=mission.id,
            details={
                "video_id": video_id,
                "locale": locale,
                "byte_size": len(media_bytes),
                "private_storage": True,
                "patient_fact_count": len(facts),
                "veo_enhanced": bool(veo_clip),
                "veo_operation_recorded": bool(veo_operation),
                "narration_status": narration_status,
                "treatment_changed": False,
            },
        )
        visible = (
            f"{_copy(locale, 'done', title=plan.title)}\n\n"
            f"[▶ {_copy(locale, 'watch')}]({public_path})\n\n"
            f"{_copy(locale, 'separation')}"
        )
        return ChatResponse(
            message=ChatMessage(
                patient_id=state.profile.id,
                role="assistant",
                author="HealthIA",
                content=visible,
                mission_id=mission.id,
                metadata={
                    "response_locale": locale,
                    "education_video": {
                        "status": "completed",
                        "video_id": video_id,
                        "topic": topic,
                        "title": plan.title,
                        "locale": locale,
                        "duration_seconds": duration_seconds,
                        "url": public_path,
                        "storage_path": storage_path,
                        "private": True,
                        "patient_fact_source_ids": [item.source_id for item in facts],
                        "veo_enhanced": bool(veo_clip),
                        "veo_operation_name": veo_operation,
                        "narration_status": narration_status,
                    },
                    "ui_action": {
                        "type": "open_education_video",
                        "url": public_path,
                        "label": _copy(locale, "watch"),
                        "locale": locale,
                        "label_es": _copy("es", "watch"),
                        "label_en": _copy("en", "watch"),
                    },
                    "external_action_executed": True,
                    "external_mutation_performed": True,
                },
            ),
            mission=mission,
        )
