from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from healthia_one.language import detect_text_language, normalize_locale
from healthia_one.models import PatientState


VIDEO_REQUEST_PATTERNS = (
    # Spanish / English
    r"\b(?:crea|creame|hazme|genera|preparame)\b.{0,36}\bvideo\b",
    r"\b(?:quiero|necesito)\b.{0,28}\bvideo\b",
    r"\b(?:explica|explicame)\b.{0,48}\ben video\b",
    r"\b(?:create|make|generate|prepare)\b.{0,36}\bvideo\b",
    r"\b(?:explain|teach me)\b.{0,48}\bin (?:a )?video\b",
    # Portuguese / French / German / Italian
    r"\b(?:crie|cria|gere|prepare|quero)\b.{0,36}\bvideo\b",
    r"\b(?:explique|expliquer|cree|creer|genere|generer|preparez|veux)\b.{0,44}\bvideo\b",
    r"\b(?:erstelle|mach|generiere|bereite)\b.{0,36}\bvideo\b",
    r"\b(?:crea|genera|prepara|voglio|spiega)\b.{0,40}\bvideo\b",
    # Script-based common forms.
    r"(?:ビデオ|動画)",
    r"(?:비디오|영상)",
    r"(?:видео)",
    r"(?:فيديو)",
    r"(?:वीडियो)",
    r"(?:视频|影片)",
)
EXPLANATION_PATTERNS = (
    r"\bexplicame\b", r"\bque significa\b", r"\bque es\b", r"\bno entiendo\b", r"\bayudame a entender\b",
    r"\bexplain\b", r"\bwhat does\b.{0,30}\bmean\b", r"\bwhat is\b", r"\bi don'?t understand\b",
    r"\bexplique\b", r"\bo que significa\b", r"\bo que e\b", r"\bnao entendo\b",
    r"\bqu'est[- ]ce que\b", r"\bque signifie\b", r"\bje ne comprends pas\b",
    r"\berklar", r"\bwas bedeutet\b", r"\bich verstehe nicht\b",
    r"\bspiega\b", r"\bcosa significa\b", r"\bcos'e\b", r"\bnon capisco\b",
    r"(?:説明|どういう意味)", r"(?:설명|무슨 뜻)", r"(?:объясни|что значит)", r"(?:اشرح|ماذا يعني)",
    r"(?:समझा|क्या मतलब)", r"(?:解释|什么意思)",
)
ACCEPT_PATTERNS = (
    r"^(?:si|sí|dale|hazlo|crealo|preparalo|por favor|claro|ok|okay)$",
    r"^(?:yes|yeah|sure|do it|make it|create it|please|go ahead)$",
    r"^(?:sim|claro|pode|faca|faça|crie|por favor)$",
    r"^(?:oui|bien sur|d'accord|faites-le|vas-y|s'il vous plait)$",
    r"^(?:ja|klar|bitte|mach es|erstell es)$",
    r"^(?:si|sì|certo|fallo|crealo|per favore)$",
    r"^(?:はい|お願い|作って)$", r"^(?:네|좋아요|만들어줘)$", r"^(?:да|сделай|пожалуйста)$",
    r"^(?:نعم|حسنا|من فضلك)$", r"^(?:हाँ|ठीक है|बनाओ)$", r"^(?:是|好的|可以|做吧)$",
)
REJECT_PATTERNS = (
    r"^(?:no|ahora no|no gracias|despues|later|not now|no thanks)$",
    r"^(?:nao|não|agora nao|agora não|nao obrigado|não obrigado)$",
    r"^(?:non|pas maintenant|non merci)$",
    r"^(?:nein|jetzt nicht|nein danke)$",
    r"^(?:no|non ora|no grazie)$",
    r"^(?:いいえ|今はいい)$", r"^(?:아니요|지금은 아니요)$", r"^(?:нет|не сейчас)$",
    r"^(?:لا|ليس الآن)$", r"^(?:नहीं|अभी नहीं)$", r"^(?:不|不要|现在不要)$",
)
GENERIC_REFERENCE = {
    "eso", "esto", "esa", "ese", "lo anterior", "that", "this", "it", "that result", "the result",
    "isso", "isto", "cela", "ça", "das", "questo",
}
MEDICATION_CHANGE_PATTERNS = (
    r"\b(?:suspende|suspender|deja de tomar|aumenta|aumentar|reduce|reducir|duplica|duplicar)\b",
    r"\b(?:stop taking|increase|decrease|double|change your dose)\b",
    r"\b(?:pare de tomar|aumente|reduza|duplique|mude a dose)\b",
    r"\b(?:arretez|augmentez|reduisez|doublez|changez la dose)\b",
    r"\b(?:absetzen|erhohen|reduzieren|verdoppeln|dosis andern)\b",
    r"\b(?:smetti di prendere|aumenta|riduci|raddoppia|cambia la dose)\b",
)


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip()


def is_english(value: str) -> bool:
    """Backward-compatible helper; new code should prefer detect_text_language."""
    return detect_text_language(value) == "en"


def is_video_request(value: str) -> bool:
    text = normalize(value)
    return any(re.search(pattern, text) for pattern in VIDEO_REQUEST_PATTERNS)


def is_explanation_request(value: str) -> bool:
    text = normalize(value)
    return any(re.search(pattern, text) for pattern in EXPLANATION_PATTERNS)


def is_acceptance(value: str) -> bool:
    text = re.sub(r"[.!?。！？]+$", "", normalize(value)).strip()
    return any(re.fullmatch(pattern, text) for pattern in ACCEPT_PATTERNS)


def is_rejection(value: str) -> bool:
    text = re.sub(r"[.!?。！？]+$", "", normalize(value)).strip()
    return any(re.fullmatch(pattern, text) for pattern in REJECT_PATTERNS)


def requested_duration_seconds(value: str, default: int = 90) -> int:
    text = normalize(value)
    match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:min|minuto|minutos|minute|minutes|minutos|minutes|minuten|minuti|分钟|분|分)\b", text)
    if match:
        minutes = float(match.group(1).replace(",", "."))
        return min(max(int(minutes * 60), 45), 300)
    if any(token in text for token in ("rapido", "corto", "quick", "short", "curto", "rapide", "kurz", "breve", "短", "짧")):
        return 60
    if any(token in text for token in ("profundo", "profundidad", "detallado", "in depth", "deep", "detalhado", "detaille", "ausfuhrlich", "dettagliato", "详细")):
        return 300
    if any(token in text for token in ("completo", "complete", "complet", "vollstandig", "completa", "完整")):
        return 180
    return min(max(int(default), 45), 300)


def _clean_topic(raw: str) -> str:
    text = str(raw or "").strip(" \t\n\r.,;:!?")
    text = re.sub(
        r"(?i)\b(?:por favor|please|por favor|s'il vous plait|bitte|per favore|un video|a video|en video|in a video|em video|explicando|que explique|sobre|acerca de|about|para entender|to explain)\b",
        " ", text,
    )
    text = re.sub(
        r"(?i)\b(?:crea|creame|hazme|genera|preparame|quiero|necesito|create|make|generate|prepare|i want|i need|explicame|explain|crie|quero|explique|cree|genere|erstelle|spiega|voglio)\b",
        " ", text,
    )
    text = re.sub(r"(?:ビデオ|動画|비디오|영상|видео|فيديو|वीडियो|视频|影片)", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -")[:180]


def topic_from_text(value: str) -> str:
    text = str(value or "").strip()
    patterns = (
        r"(?i)\b(?:sobre|acerca de|about|sobre|sur|uber|über)\s+(.+)$",
        r"(?i)\b(?:mi|my|meu|minha|mon|ma|mein|meine|mio|mia)\s+([^,.!?]{3,140})$",
        r"(?i)\b(?:explicame|explícame|explain|explique|spiega)\s+(.+?)(?:\s+en video|\s+in a video|\s+em video|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            topic = _clean_topic(match.group(1))
            if topic and normalize(topic) not in GENERIC_REFERENCE:
                return topic
    topic = _clean_topic(text)
    return "" if normalize(topic) in GENERIC_REFERENCE else topic


def latest_offer(state: PatientState) -> dict | None:
    for message in reversed(state.messages[-8:]):
        if message.role != "assistant":
            continue
        offer = (message.metadata or {}).get("education_video_offer")
        if isinstance(offer, dict) and offer.get("topic"):
            return dict(offer)
    return None


class EducationFact(BaseModel):
    key: str
    label: str
    value: str
    source_id: str
    source_type: str
    certainty: Literal["confirmed", "recorded", "patient_reported"] = "recorded"


class EducationScene(BaseModel):
    heading: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=600)
    narration: str = Field(min_length=2, max_length=1200)
    visual_kind: Literal["card", "veo"] = "card"
    veo_prompt: str = Field(default="", max_length=1200)


class EducationVideoPlan(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    summary: str = Field(default="", max_length=400)
    patient_fact_keys: list[str] = Field(default_factory=list)
    scenes: list[EducationScene] = Field(min_length=3, max_length=8)


class NarrationAudio(BaseModel):
    data: bytes
    suffix: str = ".mp3"
    mime_type: str = "audio/mpeg"


_FACT_COPY = {
    "en": {"condition": "Confirmed diagnosis in your record", "bp": "Latest recorded blood pressure", "medication": "Recorded treatment"},
    "es": {"condition": "Diagnóstico confirmado en el expediente", "bp": "Última presión registrada", "medication": "Tratamiento registrado"},
    "pt": {"condition": "Diagnóstico confirmado no prontuário", "bp": "Última pressão registrada", "medication": "Tratamento registrado"},
    "fr": {"condition": "Diagnostic confirmé dans votre dossier", "bp": "Dernière pression artérielle enregistrée", "medication": "Traitement enregistré"},
    "de": {"condition": "Bestätigte Diagnose in Ihrer Akte", "bp": "Zuletzt erfasster Blutdruck", "medication": "Dokumentierte Behandlung"},
    "it": {"condition": "Diagnosi confermata nella cartella", "bp": "Ultima pressione registrata", "medication": "Trattamento registrato"},
}


def _fact_copy(locale: str, key: str) -> str:
    language = normalize_locale(locale)
    return _FACT_COPY.get(language, _FACT_COPY["en"])[key]


def collect_topic_facts(state: PatientState, topic: str, locale: str = "es") -> list[EducationFact]:
    """Select only topic-relevant facts; never dump the whole patient chart."""
    normalized = normalize(topic)
    terms = {item for item in re.findall(r"\w+", normalized, flags=re.UNICODE) if len(item) > 2}
    facts: list[EducationFact] = []

    def related(value: str) -> bool:
        candidate = normalize(value)
        if not terms:
            return False
        candidate_terms = {item for item in re.findall(r"\w+", candidate, flags=re.UNICODE) if len(item) > 2}
        return bool(terms & candidate_terms) or any(term in candidate for term in terms)

    for index, condition in enumerate(state.profile.confirmed_conditions):
        if related(condition):
            facts.append(EducationFact(
                key=f"condition_{index}", label=_fact_copy(locale, "condition"), value=condition,
                source_id=f"profile:confirmed_condition:{index}", source_type="patient_profile", certainty="confirmed",
            ))

    bp_topic = any(term in normalized for term in (
        "hipertension", "presion", "tension", "blood pressure", "hypertension", "pressao", "hypertension arterielle",
        "blutdruck", "pressione", "давлен", "血压", "血圧", "혈압",
    ))
    if bp_topic and state.vitals:
        vital = max(state.vitals, key=lambda item: item.measured_at)
        if vital.systolic and vital.diastolic:
            facts.append(EducationFact(
                key="latest_blood_pressure", label=_fact_copy(locale, "bp"),
                value=f"{vital.systolic}/{vital.diastolic} mmHg", source_id=vital.id,
                source_type="vital_record", certainty="recorded",
            ))

    for medication in state.medication_plans:
        if not medication.active or medication.verification_status != "professional_confirmed":
            continue
        relevant = related(medication.purpose) or related(medication.name)
        if bp_topic and any(term in normalize(medication.purpose) for term in ("presion", "hipertension", "blood pressure", "pressao", "blutdruck", "pressione")):
            relevant = True
        if relevant:
            value = " ".join(part for part in (medication.name, medication.strength, medication.schedule) if str(part or "").strip()).strip()
            if value:
                facts.append(EducationFact(
                    key=f"medication_{medication.id}", label=_fact_copy(locale, "medication"), value=value,
                    source_id=medication.id, source_type="medication_plan", certainty="confirmed",
                ))

    for result in reversed(state.results[-12:]):
        matching = [item for item in result.items if related(item.name) or related(result.panel)]
        if not matching:
            continue
        for item in matching[:3]:
            facts.append(EducationFact(
                key=f"result_{result.id}_{normalize(item.name).replace(' ', '_')[:30]}",
                label=f"{result.panel}: {item.name}", value=f"{item.value} {item.unit}".strip(),
                source_id=result.id, source_type="health_result", certainty="recorded",
            ))
        break
    return facts[:5]


def validate_plan(plan: EducationVideoPlan, facts: list[EducationFact], patient_name: str) -> EducationVideoPlan:
    allowed = {item.key for item in facts}
    if any(key not in allowed for key in plan.patient_fact_keys):
        raise ValueError("Education plan referenced a patient fact outside the authorized evidence set")
    private_tokens = {normalize(patient_name)} if patient_name else set()
    private_tokens.update(normalize(item.value) for item in facts if item.value)
    veo_count = 0
    for scene in plan.scenes:
        combined = normalize(f"{scene.heading} {scene.body} {scene.narration}")
        if any(re.search(pattern, combined) for pattern in MEDICATION_CHANGE_PATTERNS):
            raise ValueError("Education plan crossed the medication-change safety boundary")
        if scene.visual_kind == "veo":
            veo_count += 1
            prompt = normalize(scene.veo_prompt)
            if not prompt:
                raise ValueError("Veo scene requires a generic prompt")
            if any(token and token in prompt for token in private_tokens):
                raise ValueError("Patient-specific information must never be sent to Veo")
            if re.search(r"\b\d+(?:[./-]\d+)*\b", prompt):
                raise ValueError("Exact numbers are not allowed in Veo education prompts")
    if veo_count > 1:
        raise ValueError("HealthIA Explain allows at most one Veo scene per video")
    return plan


_NARRATION_COPY = {
    "en": ("First, your recorded information.", "This explanation is educational and does not change your treatment or replace professional care."),
    "es": ("Primero, tu información registrada.", "Esta explicación es educativa y no cambia tu tratamiento ni sustituye la valoración de un profesional."),
    "pt": ("Primeiro, suas informações registradas.", "Esta explicação é educativa e não altera seu tratamento nem substitui o cuidado profissional."),
    "fr": ("D’abord, vos informations enregistrées.", "Cette explication est éducative et ne modifie pas votre traitement ni ne remplace un avis professionnel."),
    "de": ("Zuerst Ihre dokumentierten Informationen.", "Diese Erklärung dient der Information und ändert Ihre Behandlung nicht und ersetzt keine professionelle medizinische Betreuung."),
    "it": ("Per prima cosa, le informazioni registrate.", "Questa spiegazione è educativa, non modifica il trattamento e non sostituisce l’assistenza professionale."),
    "nl": ("Eerst uw geregistreerde informatie.", "Deze uitleg is educatief, verandert uw behandeling niet en vervangt geen professionele zorg."),
    "pl": ("Najpierw informacje zapisane w dokumentacji.", "To wyjaśnienie ma charakter edukacyjny, nie zmienia leczenia i nie zastępuje profesjonalnej opieki."),
    "ro": ("Mai întâi, informațiile înregistrate.", "Această explicație este educativă, nu vă modifică tratamentul și nu înlocuiește îngrijirea profesională."),
    "ru": ("Сначала — информация, записанная в вашей медицинской карте.", "Это образовательное объяснение не изменяет ваше лечение и не заменяет профессиональную медицинскую помощь."),
    "uk": ("Спочатку — інформація, записана у вашій медичній картці.", "Це освітнє пояснення не змінює ваше лікування і не замінює професійну медичну допомогу."),
    "tr": ("Önce kayıtlı sağlık bilgileriniz.", "Bu açıklama eğitim amaçlıdır; tedavinizi değiştirmez ve profesyonel sağlık hizmetinin yerini tutmaz."),
    "id": ("Pertama, informasi kesehatan Anda yang tercatat.", "Penjelasan ini bersifat edukatif, tidak mengubah pengobatan Anda, dan tidak menggantikan perawatan profesional."),
    "vi": ("Trước tiên là thông tin sức khỏe đã được ghi nhận của bạn.", "Phần giải thích này nhằm mục đích giáo dục, không thay đổi điều trị và không thay thế chăm sóc chuyên môn."),
    "ar": ("أولاً، معلوماتك الصحية المسجلة.", "هذا الشرح للتثقيف ولا يغيّر علاجك ولا يحل محل الرعاية الطبية المتخصصة."),
    "hi": ("पहले, आपकी दर्ज की गई स्वास्थ्य जानकारी।", "यह व्याख्या केवल शिक्षा के लिए है; यह आपके उपचार को नहीं बदलती और पेशेवर चिकित्सा देखभाल का स्थान नहीं लेती।"),
    "ja": ("まず、記録されているあなたの健康情報です。", "この説明は教育目的であり、治療内容を変更するものでも、専門的な医療の代わりになるものでもありません。"),
    "ko": ("먼저 기록된 건강 정보입니다.", "이 설명은 교육 목적이며 치료를 변경하지 않고 전문 의료를 대신하지 않습니다."),
    "zh": ("首先，这是您已记录的健康信息。", "本说明仅用于健康教育，不会改变您的治疗方案，也不能替代专业医疗服务。"),
}


def compose_narration(plan: EducationVideoPlan, facts: list[EducationFact], locale: str) -> str:
    language = normalize_locale(locale)
    intro, ending = _NARRATION_COPY.get(language, _NARRATION_COPY["en"])
    selected = {item.key: item for item in facts if item.key in plan.patient_fact_keys}
    parts: list[str] = []
    if selected:
        rendered = "; ".join(f"{fact.label}: {fact.value}" for fact in selected.values())
        parts.append(f"{intro} {rendered}.")
    parts.extend(scene.narration.strip() for scene in plan.scenes)
    parts.append(ending)
    # Long narration is chunked safely by GoogleEducationMediaProvider, so do
    # not truncate clinically useful content here.
    return " ".join(part for part in parts if part).strip()
