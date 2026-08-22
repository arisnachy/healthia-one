from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


path = Path("deployment/deploy-cloud-demo.ps1")
text = path.read_text("utf-8")
anchor = '''if ($LASTEXITCODE -ne 0) {
    Write-Host "Creando Firestore Native (default)..." -ForegroundColor Cyan
    & gcloud firestore databases create --database="(default)" --location=$FirestoreLocation --type=firestore-native --project $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear Firestore (default)." }
}

'''
replacement = anchor + '''# Ephemeral multi-instance coordination documents have explicit retention.
# Firestore TTL activation is asynchronous and can take several minutes, but the
# policy update command itself must be accepted before this deployment proceeds.
foreach ($ttlPolicy in @(
    @{ Field = "ttl_at"; Collection = "healthia_device_pairings" },
    @{ Field = "expires_at"; Collection = "healthia_stream_events" }
)) {
    Write-Host "Asegurando TTL Firestore: $($ttlPolicy.Collection).$($ttlPolicy.Field)..." -ForegroundColor Cyan
    & gcloud firestore fields ttls update $ttlPolicy.Field `
        --collection-group=$($ttlPolicy.Collection) `
        --database="(default)" `
        --project $ProjectId `
        --enable-ttl `
        --async `
        --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo asegurar TTL para $($ttlPolicy.Collection).$($ttlPolicy.Field)."
    }
}

'''
text = replace_once(text, anchor, replacement, "Firestore TTL insertion")
path.write_text(text, "utf-8")
print("HEALTHIA_FIRESTORE_TTL_PATCH_PASS")
