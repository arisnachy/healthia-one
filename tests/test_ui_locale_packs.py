import json
import re
from pathlib import Path


def _packs():
    text = Path("web/i18n-packs.js").read_text(encoding="utf-8")
    payload = text.removeprefix("window.HealthIAExtraDictionaries = Object.freeze(").removesuffix(");\n")
    return json.loads(payload)


def test_static_ui_packs_cover_supported_operating_system_locales():
    packs = _packs()
    assert set(packs) == {"pt","fr","de","it","nl","pl","ro","tr","id","vi","ru","uk","ar","hi","ja","ko","zh"}
    english = re.search(r"en: (\{.*?\})\s*,\s*es:", Path("web/i18n.js").read_text(encoding="utf-8"), re.S)
    assert english
    base = json.loads(english.group(1))
    for locale, pack in packs.items():
        for key in base:
            assert key in pack, f"{locale} missing {key}"
        assert pack["auth.hero"].strip()
        assert pack["chat.hero"].strip()


def test_patient_entry_loads_locale_packs_before_i18n_runtime():
    for filename in ("web/login.html", "web/index.html"):
        html = Path(filename).read_text(encoding="utf-8")
        assert html.index("/assets/i18n-packs.js") < html.index("/assets/i18n.js")


def test_healthia_explain_renderer_receives_resolved_content_locale():
    source = Path("healthia_one/education_video.py").read_text(encoding="utf-8")
    assert "locale=locale" in source
