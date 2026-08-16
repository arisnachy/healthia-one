from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deployment" / "promote-google-live-prereqs.ps1"
RUNTIME = ROOT / "healthia_one" / "google_constellation_runtime.py"


def test_live_prerequisite_probes_support_windows_powershell_and_cloud_run() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "Invoke-WebRequest" not in source
    assert "[System.Net.HttpWebRequest]::Create" in source
    assert "MethodInvocationException" not in source
    assert "while ($webException" in source
    assert '$readiness = Probe "/api/readiness"' in source
    assert '$healthz = Probe "/healthz"' in source
    assert "if ($readiness -ne 200 -or $login -ne 200 -or $session -ne 200)" in source


def test_live_prerequisite_probes_keep_all_patient_routes_fail_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for route in (
        "/api/bootstrap",
        "/api/opportunities",
        "/api/google-constellation/capabilities",
        "/api/google-constellation/oauth/readiness",
    ):
        assert f'Probe "{route}"' in source
    assert "$bootstrap -ne 401" in source
    assert "$opportunities -ne 401" in source
    assert "$googleCaps -ne 401" in source
    assert "$oauthReadiness -ne 401" in source


def test_live_promotion_refuses_the_private_backend_and_unrestricted_keys() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '$WebServiceName -ne "healthia-one-web-demo"' in source
    assert "refusing to expose any other Cloud Run service" in source
    assert "apiTargets.Count -ne 1" in source
    assert "restricted exclusively to places.googleapis.com" in source


def test_places_key_is_written_from_memory_without_a_windows_powershell_bom() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "function Add-SecretVersionFromMemory" in source
    assert "$process.StandardInput.Write($Payload)" in source
    assert "$Payload = $Payload.TrimStart([char] 0xFEFF)" in source
    assert ").Trim().TrimStart([char] 0xFEFF)" in source
    assert "$mapsKey | & gcloud secrets versions add" not in source
    assert "can prepend a BOM" in source

    runtime = RUNTIME.read_text(encoding="utf-8")
    assert '.strip().lstrip("\\ufeff")' in runtime
