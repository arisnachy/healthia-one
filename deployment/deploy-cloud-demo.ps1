param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$VertexLocation = "global",
    [string]$FirestoreLocation = "nam5",
    [string]$BucketLocation = "US",
    [string]$BucketName = "",
    [string]$ServiceName = "healthia-one-demo",
    [string]$RuntimeServiceAccount = "healthia-one-demo",
    [string]$BuildServiceAccount = "healthia-one-build",
    [string]$DeviceSecretName = "healthia-device-token-secret",
    [string]$SessionSecretName = "healthia-session-secret",
    [ValidateRange(8, 40)][int]$RequestLimit = 20,
    [ValidateRange(256, 4096)][int]$MaxOutputTokens = 1400,
    [switch]$PublicDemo,
    [switch]$SkipStrictProof,
    [switch]$Confirmed
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
$BuildServiceAccountEmail = "$BuildServiceAccount@$ProjectId.iam.gserviceaccount.com"
$BuildServiceAccountResource = "projects/$ProjectId/serviceAccounts/$BuildServiceAccountEmail"

function New-CryptoSecretValue {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    }
    finally {
        $rng.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Ensure-Secret([string]$Name, [string]$Purpose) {
    & gcloud secrets describe $Name --project $ProjectId --format "value(name)" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return }

    Write-Host "Creando secreto criptografico para $Purpose..." -ForegroundColor Cyan
    $secretValue = New-CryptoSecretValue
    try {
        $secretValue | & gcloud secrets create $Name `
            --project $ProjectId `
            --replication-policy="automatic" `
            --data-file=- | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear $Name." }
    }
    finally {
        $secretValue = $null
    }
}

function Ensure-ServiceAccount([string]$AccountId, [string]$Email, [string]$DisplayName) {
    & gcloud iam service-accounts describe $Email --project $ProjectId --format "value(email)" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return }

    & gcloud iam service-accounts create $AccountId `
        --project $ProjectId `
        --display-name $DisplayName | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la cuenta de servicio $AccountId." }
}

function Grant-ProjectRole([string]$Email, [string]$Role) {
    & gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$Email" `
        --role $Role `
        --condition=None `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo asignar $Role a $Email." }
}

Write-Host "HEALTHIA ONE - CLOUD / VERTEX HACKATHON PROOF" -ForegroundColor Cyan
Write-Host "Proyecto: $ProjectId" -ForegroundColor White
Write-Host "Cloud Run: $ServiceName ($Region)" -ForegroundColor White
Write-Host "Vertex AI: Gemini 3.5 Flash ($VertexLocation), ADC por identidad de servicio" -ForegroundColor White
Write-Host "Firestore: (default) ($FirestoreLocation)" -ForegroundColor White
Write-Host "Evidencia clinica: gs://$BucketName ($BucketLocation)" -ForegroundColor White
Write-Host "Build SA: $BuildServiceAccountEmail" -ForegroundColor White
Write-Host "Runtime SA: $RuntimeServiceAccountEmail" -ForegroundColor White
Write-Host "Cloud Run: min 0, max 1; agentes a demanda y proactive=false." -ForegroundColor Green
Write-Host "Google AI: maximo $RequestLimit solicitudes por proceso y $MaxOutputTokens tokens de salida." -ForegroundColor Green
Write-Host "No se inyecta GEMINI_API_KEY: Cloud Run usa su service account para Vertex AI." -ForegroundColor Green

if (-not $Confirmed) {
    $confirmation = Read-Host "Escribe DEPLOY para aprovisionar/desplegar y probar"
    if ($confirmation -ne "DEPLOY") { throw "Despliegue cancelado." }
}

& gcloud config set project $ProjectId | Out-Host
if ($LASTEXITCODE -ne 0) { throw "No se pudo seleccionar el proyecto." }

# The GitHub provisioning identity intentionally does not need permission to
# enable project services. The hackathon project is preconfigured; if any
# required API below is unavailable, the first dependent gcloud operation fails
# closed and the Cloud proof is not counted.
$apis = @(
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com"
)
Write-Host "Usando APIs preconfiguradas (sin serviceusage.services.enable):" -ForegroundColor Cyan
foreach ($api in $apis) {
    Write-Host "- $api" -ForegroundColor DarkGray
}

Ensure-Secret $DeviceSecretName "identidad durable de dispositivos"
Ensure-Secret $SessionSecretName "sesiones firmadas de pacientes"

Ensure-ServiceAccount $BuildServiceAccount $BuildServiceAccountEmail "HealthIA ONE Cloud Build"
Ensure-ServiceAccount $RuntimeServiceAccount $RuntimeServiceAccountEmail "HealthIA ONE demo runtime"

# Build identity: only what source deployment needs. We specify it explicitly so
# the proof never depends on whichever default Cloud Build SA the project uses.
Grant-ProjectRole $BuildServiceAccountEmail "roles/run.builder"

# Runtime identity: least-privilege application access. It receives no deploy or
# project-IAM administration role.
foreach ($role in @(
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor"
)) {
    Grant-ProjectRole $RuntimeServiceAccountEmail $role
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
    "HEALTHIA_MODEL=gemini-3.5-flash",
    "HEALTHIA_STORE_BACKEND=firestore",
    "HEALTHIA_AUTH_REQUIRED=true",
    "HEALTHIA_ALLOW_REGISTRATION=true",
    "HEALTHIA_COST_MODE=cloud_demo",
    "HEALTHIA_AI_REQUEST_LIMIT=$RequestLimit",
    "HEALTHIA_LLM_TIMEOUT_SECONDS=60",
    "HEALTHIA_COST_GUARD_START_ENABLED=true",
    "HEALTHIA_COST_CONTROL_UI=false",
    "HEALTHIA_AI_MAX_OUTPUT_TOKENS=$MaxOutputTokens",
    "HEALTHIA_PROACTIVE_ENABLED=false",
    "HEALTHIA_GCS_BUCKET=$BucketName",
    "GOOGLE_GENAI_USE_VERTEXAI=true",
    "GOOGLE_CLOUD_PROJECT=$ProjectId",
    "GOOGLE_CLOUD_LOCATION=$VertexLocation"
) -join ","

$args = @(
    "run", "deploy", $ServiceName,
    "--source", ".",
    "--build-service-account", $BuildServiceAccountResource,
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
    "--set-secrets", "HEALTHIA_DEVICE_TOKEN_SECRET=${DeviceSecretName}:latest,HEALTHIA_SESSION_SECRET=${SessionSecretName}:latest",
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
    Write-Host "Prueba estricta: Cloud Run + auth A/B + Gemini 3.5/ADK + Firestore + GCS + gemelo..." -ForegroundColor Cyan
    & python @proofArgs | Tee-Object -FilePath "deployment/cloud-proof-latest.json" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "El despliegue existe pero NO supero la prueba estricta. No lo declares probado."
    }
}

Write-Host ""
Write-Host "CLOUD REAL PROBADO: $url" -ForegroundColor Green
Write-Host "Captura Cloud Run revision $revision, Vertex AI/Cloud Logging y deployment/cloud-proof-latest.json para el demo." -ForegroundColor Cyan
Write-Host "Al terminar puedes eliminar solo Cloud Run (manteniendo evidencia) con:" -ForegroundColor Yellow
Write-Host ".\deployment\remove-cloud-demo.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -BucketName $BucketName" -ForegroundColor Yellow
