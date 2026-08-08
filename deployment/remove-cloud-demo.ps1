param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$DeviceSecretName = "healthia-device-token-secret",
    [string]$SessionSecretName = "healthia-session-secret",
    [string]$BucketName = "",
    [string]$RuntimeServiceAccount = "healthia-one-demo",
    [string]$BuildServiceAccount = "healthia-one-build",
    [switch]$DeleteBucket,
    [switch]$DeleteSecret,
    [switch]$DeleteRuntimeServiceAccount,
    [switch]$DeleteBuildServiceAccount,
    [switch]$DeleteProject,
    [switch]$Confirmed
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI no esta instalado o no esta en PATH."
}
if ([string]::IsNullOrWhiteSpace($BucketName)) {
    $BucketName = "$ProjectId-healthia-evidence"
}
$RuntimeServiceAccountEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
$BuildServiceAccountEmail = "$BuildServiceAccount@$ProjectId.iam.gserviceaccount.com"

Write-Host "Se eliminara el servicio Cloud Run $ServiceName del proyecto $ProjectId." -ForegroundColor Yellow
if ($DeleteBucket) {
    Write-Host "Tambien se eliminara gs://$BucketName y TODA la evidencia sintetica de demo que contenga." -ForegroundColor Red
}
if ($DeleteSecret) {
    Write-Host "Tambien se eliminaran $DeviceSecretName y $SessionSecretName." -ForegroundColor Red
}
if ($DeleteRuntimeServiceAccount) {
    Write-Host "Tambien se eliminara la identidad de runtime $RuntimeServiceAccountEmail." -ForegroundColor Red
}
if ($DeleteBuildServiceAccount) {
    Write-Host "Tambien se eliminara la identidad de build $BuildServiceAccountEmail." -ForegroundColor Red
}
if ($DeleteProject) {
    Write-Host "Tambien se programara la eliminacion COMPLETA del proyecto." -ForegroundColor Red
}
if (-not $Confirmed) {
    $confirmation = Read-Host "Escribe DELETE para continuar"
    if ($confirmation -ne "DELETE") { throw "Limpieza cancelada." }
}

& gcloud run services delete $ServiceName --project $ProjectId --region $Region --quiet | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cloud Run no confirmo la eliminacion; revisa si el servicio ya no existe." -ForegroundColor Yellow
}

if ($DeleteBucket) {
    & gcloud storage rm --recursive "gs://$BucketName/**" --project $ProjectId 2>$null | Out-Host
    & gcloud storage buckets delete "gs://$BucketName" --project $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo eliminar el bucket o ya no existe." -ForegroundColor Yellow
    }
}

if ($DeleteSecret) {
    foreach ($name in @($DeviceSecretName, $SessionSecretName)) {
        & gcloud secrets delete $name --project $ProjectId --quiet | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host "No se pudo eliminar $name o ya no existe." -ForegroundColor Yellow
        }
    }
}

if ($DeleteRuntimeServiceAccount) {
    & gcloud iam service-accounts delete $RuntimeServiceAccountEmail --project $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo eliminar la cuenta de runtime o ya no existe." -ForegroundColor Yellow
    }
}

if ($DeleteBuildServiceAccount) {
    & gcloud iam service-accounts delete $BuildServiceAccountEmail --project $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo eliminar la cuenta de build o ya no existe." -ForegroundColor Yellow
    }
}

if ($DeleteProject) {
    & gcloud projects delete $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo programar la eliminacion del proyecto." }
    Write-Host "Proyecto programado para eliminacion." -ForegroundColor Green
} else {
    Write-Host "Cloud Run eliminado." -ForegroundColor Green
    Write-Host "Firestore, secretos, bucket, Artifact Registry e identidades siguen existiendo salvo eliminacion explicita." -ForegroundColor Yellow
    Write-Host "Revisa Cloud Billing y Resource Manager. Usa -DeleteProject solo si el proyecto es descartable." -ForegroundColor Yellow
}
