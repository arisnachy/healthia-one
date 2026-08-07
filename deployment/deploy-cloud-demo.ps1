param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$FirestoreLocation = "nam5",
    [string]$BucketLocation = "US",
    [string]$BucketName = "",
    [string]$ServiceName = "healthia-one-demo",
    [string]$RuntimeServiceAccount = "healthia-one-demo",
    [string]$SecretName = "healthia-gemini-api-key",
    [string]$DeviceSecretName = "healthia-device-token-secret",
    [ValidateRange(2, 25)][int]$RequestLimit = 20,
    [ValidateRange(64, 2048)][int]$MaxOutputTokens = 700,
    [switch]$PublicDemo,
    [switch]$SkipStrictProof
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI no esta instalado o no esta en PATH."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python no esta instalado o no esta en PATH."
}
if ([string]::IsNullOrWhiteSpace($BucketName)) {
    $BucketName = "$ProjectId-healthia-evidence"
}
$RuntimeServiceAccountEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"

Write-Host "MODO DEMO CLOUD VERIFICABLE" -ForegroundColor Cyan
Write-Host "Proyecto: $ProjectId" -ForegroundColor White
Write-Host "Cloud Run: $ServiceName ($Region)" -ForegroundColor White
Write-Host "Firestore: (default) ($FirestoreLocation)" -ForegroundColor White
Write-Host "Evidencia clinica: gs://$BucketName ($BucketLocation)" -ForegroundColor White
Write-Host "Runtime SA: $RuntimeServiceAccountEmail" -ForegroundColor White
Write-Host "Cloud Run: min 0, max 1, facturacion por solicitud." -ForegroundColor Green
Write-Host "Google AI: maximo $RequestLimit solicitudes por proceso y $MaxOutputTokens tokens de salida." -ForegroundColor Green
Write-Host "La prueba estricta consumira al menos 2 solicitudes Gemini: probe + PDF multimodal sintetico." -ForegroundColor Yellow
Write-Host "El limite por proceso se reinicia si Cloud Run reinicia la instancia; conserva budgets/quota del proyecto." -ForegroundColor Yellow

$confirmation = Read-Host "Escribe DEPLOY para aprovisionar/desplegar y probar"
if ($confirmation -ne "DEPLOY") {
    throw "Despliegue cancelado."
}

& gcloud config set project $ProjectId | Out-Host
if ($LASTEXITCODE -ne 0) { throw "No se pudo seleccionar el proyecto." }

Write-Host "Activando APIs necesarias..." -ForegroundColor Cyan
$apis = @(
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com"
)
& gcloud services enable @apis --project $ProjectId | Out-Host
if ($LASTEXITCODE -ne 0) { throw "No se pudieron activar las APIs necesarias." }

& gcloud secrets describe $SecretName --project $ProjectId --format "value(name)" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "No existe el secreto $SecretName. Crea el secreto con la API key de Gemini antes de desplegar; el script nunca acepta ni imprime la clave."
}

& gcloud secrets describe $DeviceSecretName --project $ProjectId --format "value(name)" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creando secreto criptografico para identidad durable de dispositivos..." -ForegroundColor Cyan
    $secretBytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
    $deviceSecretValue = [Convert]::ToBase64String($secretBytes)
    $deviceSecretValue | & gcloud secrets create $DeviceSecretName `
        --project $ProjectId `
        --replication-policy="automatic" `
        --data-file=- | Out-Null
    $deviceSecretValue = $null
    $secretBytes = $null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear $DeviceSecretName." }
}

& gcloud iam service-accounts describe $RuntimeServiceAccountEmail --project $ProjectId --format "value(email)" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    & gcloud iam service-accounts create $RuntimeServiceAccount --project $ProjectId --display-name "HealthIA ONE demo runtime" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la cuenta de servicio de runtime." }
}

foreach ($role in @("roles/datastore.user", "roles/storage.objectAdmin", "roles/secretmanager.secretAccessor")) {
    & gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$RuntimeServiceAccountEmail" `
        --role $role `
        --condition=None `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo asignar $role a $RuntimeServiceAccountEmail." }
}

& gcloud firestore databases describe --database="(default)" --project $ProjectId --format "value(name)" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creando Firestore Native (default)..." -ForegroundColor Cyan
    & gcloud firestore databases create --database="(default)" --location=$FirestoreLocation --type=firestore-native --project $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear Firestore (default)." }
}

& gcloud storage buckets describe "gs://$BucketName" --project $ProjectId --format "value(name)" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creando bucket privado de evidencia..." -ForegroundColor Cyan
    & gcloud storage buckets create "gs://$BucketName" `
        --project $ProjectId `
        --location $BucketLocation `
        --default-storage-class STANDARD `
        --uniform-bucket-level-access `
        --public-access-prevention | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear gs://$BucketName." }
}

$envVars = @(
    "HEALTHIA_ENV=cloud",
    "HEALTHIA_LLM_BACKEND=gemini_api",
    "HEALTHIA_STORE_BACKEND=firestore",
    "HEALTHIA_COST_MODE=cloud_demo",
    "HEALTHIA_AI_REQUEST_LIMIT=$RequestLimit",
    "HEALTHIA_COST_GUARD_START_ENABLED=true",
    "HEALTHIA_COST_CONTROL_UI=false",
    "HEALTHIA_AI_MAX_OUTPUT_TOKENS=$MaxOutputTokens",
    "HEALTHIA_PROACTIVE_ENABLED=false",
    "HEALTHIA_GCS_BUCKET=$BucketName",
    "GOOGLE_CLOUD_PROJECT=$ProjectId"
) -join ","

$args = @(
    "run", "deploy", $ServiceName,
    "--source", ".",
    "--project", $ProjectId,
    "--region", $Region,
    "--service-account", $RuntimeServiceAccountEmail,
    "--min", "0",
    "--max", "1",
    "--concurrency", "20",
    "--cpu", "1",
    "--memory", "512Mi",
    "--timeout", "600",
    "--set-env-vars", $envVars,
    "--set-secrets", "GEMINI_API_KEY=${SecretName}:latest,HEALTHIA_DEVICE_TOKEN_SECRET=${DeviceSecretName}:latest",
    "--quiet"
)

if ($PublicDemo) {
    $args += "--allow-unauthenticated"
} else {
    $args += "--no-allow-unauthenticated"
}

Write-Host "Desplegando Cloud Run..." -ForegroundColor Cyan
& gcloud @args | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Cloud Run no pudo desplegar HealthIA." }

$url = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)").Trim()
$revision = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.latestReadyRevisionName)").Trim()
if ([string]::IsNullOrWhiteSpace($url) -or [string]::IsNullOrWhiteSpace($revision)) {
    throw "Cloud Run no devolvio URL/revision lista."
}

Write-Host "Cloud Run listo: $url" -ForegroundColor Green
Write-Host "Revision: $revision" -ForegroundColor Green

if (-not $SkipStrictProof) {
    $identityToken = ""
    if (-not $PublicDemo) {
        $identityToken = (& gcloud auth print-identity-token).Trim()
        if ([string]::IsNullOrWhiteSpace($identityToken)) {
            throw "No se pudo obtener identity token para probar el servicio privado."
        }
    }
    $proofArgs = @(
        "deployment/verify_cloud_demo.py",
        "--url", $url,
        "--project", $ProjectId,
        "--bucket", $BucketName,
        "--json"
    )
    if (-not [string]::IsNullOrWhiteSpace($identityToken)) {
        $proofArgs += @("--identity-token", $identityToken)
    }
    Write-Host "Ejecutando prueba estricta Cloud Run + Firestore + GCS + Gemini..." -ForegroundColor Cyan
    & python @proofArgs | Tee-Object -FilePath "deployment/cloud-proof-latest.json" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "El despliegue existe pero NO supero la prueba estricta. No lo declares probado."
    }
}

Write-Host ""
Write-Host "CLOUD REAL PROBADO: $url" -ForegroundColor Green
Write-Host "Captura Cloud Run revision $revision, Cloud Logging y deployment/cloud-proof-latest.json para el demo." -ForegroundColor Cyan
Write-Host "Al terminar, elimina el servicio y opcionalmente el bucket con:" -ForegroundColor Yellow
Write-Host ".\deployment\remove-cloud-demo.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -BucketName $BucketName" -ForegroundColor Yellow
