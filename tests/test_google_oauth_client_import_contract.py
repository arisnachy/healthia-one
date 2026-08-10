from pathlib import Path


SCRIPT = Path("deployment/import-google-oauth-client.ps1").read_text(encoding="utf-8")


def test_oauth_client_payload_uses_redirected_stdin_without_powershell_pipeline() -> None:
    assert "Add-SecretVersionFromMemory $SecretName $compact" in SCRIPT
    assert "$compact | & gcloud" not in SCRIPT
    assert "$process.StandardInput.Write($Payload)" in SCRIPT
    assert "$startInfo.RedirectStandardInput = $true" in SCRIPT
    assert "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)" in SCRIPT
    assert "[Console]::InputEncoding = $previousInputEncoding" in SCRIPT
    assert '"platform\\bundledpython\\python.exe"' in SCRIPT
    assert '"lib\\gcloud.py"' in SCRIPT
    assert "UTF-8 BOM" in SCRIPT


def test_oauth_client_import_never_logs_payload_or_secret_fields() -> None:
    assert "OAuth client payload: not displayed" in SCRIPT
    assert "client_secret: $clientSecret" not in SCRIPT
    assert "client_id: $clientId" not in SCRIPT
    assert 'Get-Command "gcloud.cmd"' in SCRIPT
