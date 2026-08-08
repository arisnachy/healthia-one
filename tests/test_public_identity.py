from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

INTERNAL_AGENT_NAMES = (
    "KIRA",
    "HISTORIA",
    "SENTINEL",
    "LUMEN",
    "VITA",
    "NAVIGATOR",
    "HEREDITAS",
    "ARCHIVUM",
    "MEDSAFE",
    "ADVOCATE",
    "BASTION",
)


def patient_surface() -> str:
    # Only executable and rendered patient surfaces are scanned. CSS comments are
    # implementation documentation and cannot appear in the browser interface.
    sources = sorted([*WEB.glob("*.html"), *WEB.glob("*.js")])
    return "\n".join(path.read_text(encoding="utf-8") for path in sources)


def test_patient_surface_does_not_expose_internal_agent_names() -> None:
    public_surface = patient_surface()
    for name in INTERNAL_AGENT_NAMES:
        assert name not in public_surface


def test_patient_interface_uses_clear_patient_language() -> None:
    public_surface = patient_surface()
    for marker in (
        "HealthIA",
        "Tu salud no vuelve a empezar desde cero",
        "Resultados",
        "Mi expediente",
        "Misiones de salud",
        "Cuenta y configuración",
        "Permisos y privacidad",
        "Dispositivos",
        "Preguntas creadas para este caso",
        "Continuar con las 3 restantes",
        "No pude completar las próximas preguntas personalizadas",
        "Lo que hice",
    ):
        assert marker in public_surface
    for technical_marker in ("Gemini + ADK", "Google AI está tardando", "Google AI/ADK"):
        assert technical_marker not in public_surface


def test_documentation_does_not_reference_deleted_version_layers() -> None:
    checked = [ROOT / "README.md", ROOT / "docs" / "ARCHITECTURE.md"]
    content = "\n".join(path.read_text(encoding="utf-8") for path in checked)
    for version in range(2, 8):
        assert f"ui-v{version}" not in content
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for script in (
        "app.js",
        "patient-record.js",
        "family-documents.js",
        "continuity.js",
        "privacy-controls.js",
        "profile-devices.js",
        "icons.js",
    ):
        assert f"node --check web/{script}" in readme
