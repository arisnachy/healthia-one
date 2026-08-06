param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$SecretName = "healthia-gemini-api-key",
    [switch]$DeleteSecret,
    [switch]$DeleteProject
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI no esta instalado o no esta en PATH."
}

Write-Host "Se eliminara el servicio Cloud Run $ServiceName del proyecto $ProjectId." -ForegroundColor Yellow
if ($DeleteProject) {
    Write-Host "Tambien se programara la eliminacion COMPLETA del proyecto." -ForegroundColor Red
}
$confirmation = Read-Host "Escribe DELETE para continuar"
if ($confirmation -ne "DELETE") {
    throw "Limpieza cancelada."
}

& gcloud run services delete $ServiceName --project $ProjectId --region $Region --quiet | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cloud Run no confirmo la eliminacion; revisa si el servicio ya no existe." -ForegroundColor Yellow
}

if ($DeleteSecret) {
    & gcloud secrets delete $SecretName --project $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo eliminar el secreto o ya no existe." -ForegroundColor Yellow
    }
}

if ($DeleteProject) {
    & gcloud projects delete $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo programar la eliminacion del proyecto." }
    Write-Host "Proyecto programado para eliminacion." -ForegroundColor Green
} else {
    Write-Host "Servicio Cloud Run eliminado. Firestore, secretos, Artifact Registry y otros recursos pueden seguir existiendo." -ForegroundColor Green
    Write-Host "Revisa Cloud Billing y Resource Manager. Usa -DeleteProject para la limpieza total del proyecto de demo." -ForegroundColor Yellow
}
