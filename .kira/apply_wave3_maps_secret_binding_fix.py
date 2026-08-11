from pathlib import Path

DEPLOY = Path('deployment/deploy-cloud-demo.ps1')
TEST = Path('tests/test_wave3_repro_hardening.py')

text = DEPLOY.read_text(encoding='utf-8')

param_anchor = '    [string]$SessionSecretName = "healthia-session-secret",\n    [ValidateRange(8, 40)][int]$RequestLimit = 20,'
param_replacement = '    [string]$SessionSecretName = "healthia-session-secret",\n    [string]$MapsSecretName = "healthia-google-maps-api-key",\n    [ValidateRange(8, 40)][int]$RequestLimit = 20,'
if text.count(param_anchor) != 1:
    raise SystemExit('Maps secret parameter anchor mismatch')
text = text.replace(param_anchor, param_replacement, 1)

secret_check_anchor = 'Ensure-Secret $DeviceSecretName "identidad durable de dispositivos"\nEnsure-Secret $SessionSecretName "sesiones firmadas de pacientes"\n\nEnsure-ServiceAccount'
secret_check_replacement = '''Ensure-Secret $DeviceSecretName "identidad durable de dispositivos"
Ensure-Secret $SessionSecretName "sesiones firmadas de pacientes"

# Maps is an existing provider credential. Never manufacture or print it here:
# require an enabled Secret Manager version and mount it directly into Cloud Run.
$mapsSecretState = (& gcloud secrets versions describe latest `
    --secret $MapsSecretName `
    --project $ProjectId `
    --format "value(state)" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $mapsSecretState -ne "ENABLED") {
    throw "Google Maps Secret Manager binding is unavailable or not enabled."
}
Write-Host "Google Maps: using existing Secret Manager binding (value not exposed)." -ForegroundColor Green

Ensure-ServiceAccount'''
if text.count(secret_check_anchor) != 1:
    raise SystemExit('Maps secret validation anchor mismatch')
text = text.replace(secret_check_anchor, secret_check_replacement, 1)

binding_anchor = '    "--set-secrets", "HEALTHIA_DEVICE_TOKEN_SECRET=${DeviceSecretName}:latest,HEALTHIA_SESSION_SECRET=${SessionSecretName}:latest",'
binding_replacement = '    "--set-secrets", "HEALTHIA_DEVICE_TOKEN_SECRET=${DeviceSecretName}:latest,HEALTHIA_SESSION_SECRET=${SessionSecretName}:latest,GOOGLE_MAPS_API_KEY=${MapsSecretName}:latest",'
if text.count(binding_anchor) != 1:
    raise SystemExit('Cloud Run secret binding anchor mismatch')
text = text.replace(binding_anchor, binding_replacement, 1)
DEPLOY.write_text(text, encoding='utf-8')

test = TEST.read_text(encoding='utf-8')
new_test = '''\n\ndef test_wave3_cloud_demo_mounts_existing_maps_key_from_secret_manager() -> None:\n    deploy = (ROOT / "deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")\n    assert '[string]$MapsSecretName = "healthia-google-maps-api-key"' in deploy\n    assert 'gcloud secrets versions describe latest' in deploy\n    assert '--secret $MapsSecretName' in deploy\n    assert '$mapsSecretState -ne "ENABLED"' in deploy\n    assert 'GOOGLE_MAPS_API_KEY=${MapsSecretName}:latest' in deploy\n    assert 'Google Maps: using existing Secret Manager binding (value not exposed).' in deploy\n    assert 'GOOGLE_MAPS_API_KEY=' not in deploy.split('$envVars = @(', 1)[1].split(') -join', 1)[0]\n'''
if 'test_wave3_cloud_demo_mounts_existing_maps_key_from_secret_manager' in test:
    raise SystemExit('Maps secret binding regression already exists')
TEST.write_text(test.rstrip() + new_test + '\n', encoding='utf-8')
