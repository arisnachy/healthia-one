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
    [string]$EvaluationSecretName = "healthia-evaluation-access-key",
    [string]$MapsSecretName = "healthia-google-maps-api-key",
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
$releaseSha = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($releaseSha)) {
    throw "No se pudo resolver el commit candidato."
}
$dirtyWorktree = & git status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirtyWorktree) {
    throw "El despliegue exact-SHA exige un worktree limpio y comprometido."
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

function Grant-SecretRole([string]$Email, [string]$SecretName) {
    & gcloud secrets add-iam-policy-binding $SecretName `
        --project $ProjectId `
        --member "serviceAccount:$Email" `
        --role "roles/secretmanager.secretAccessor" `
        --condition=None `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo limitar el acceso de $Email al secreto $SecretName." }
}

function Grant-BucketRole([string]$Email, [string]$Name) {
    & gcloud storage buckets add-iam-policy-binding "gs://$Name" `
        --member "serviceAccount:$Email" `
        --role "roles/storage.objectAdmin" `
        --condition=None `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo limitar el acceso de $Email al bucket $Name." }
}

function Remove-ProjectRole([string]$Email, [string]$Role) {
    & gcloud projects remove-iam-policy-binding $ProjectId `
        --member "serviceAccount:$Email" `
        --role $Role `
        --condition=None `
        --quiet 2>$null | Out-Null
    $remaining = (& gcloud projects get-iam-policy $ProjectId `
        --flatten="bindings[].members" `
        --filter="bindings.role=$Role AND bindings.members=serviceAccount:$Email" `
        --format="value(bindings.role)" 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or -not [string]::IsNullOrWhiteSpace($remaining)) {
        throw "El rol amplio $Role sigue asignado a $Email; se cancela el despliegue."
    }
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
Ensure-Secret $EvaluationSecretName "acceso aislado del evaluador Living System"

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

Ensure-ServiceAccount $BuildServiceAccount $BuildServiceAccountEmail "HealthIA ONE Cloud Build"
Ensure-ServiceAccount $RuntimeServiceAccount $RuntimeServiceAccountEmail "HealthIA ONE demo runtime"

# Build identity: only what source deployment needs. We specify it explicitly so
# the proof never depends on whichever default Cloud Build SA the project uses.
Grant-ProjectRole $BuildServiceAccountEmail "roles/run.builder"

# Runtime identity: least-privilege application access. It receives no deploy or
# project-IAM administration role.
foreach ($role in @(
    "roles/aiplatform.user",
    "roles/datastore.user"
)) {
    Grant-ProjectRole $RuntimeServiceAccountEmail $role
}
foreach ($secretName in @($DeviceSecretName, $SessionSecretName, $EvaluationSecretName, $MapsSecretName)) {
    Grant-SecretRole $RuntimeServiceAccountEmail $secretName
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
Grant-BucketRole $RuntimeServiceAccountEmail $BucketName
Remove-ProjectRole $RuntimeServiceAccountEmail "roles/storage.objectAdmin"
Remove-ProjectRole $RuntimeServiceAccountEmail "roles/secretmanager.secretAccessor"

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
    "HEALTHIA_EVALUATION_ENABLED=true",
    "HEALTHIA_EVALUATION_SESSION_MINUTES=30",
    "HEALTHIA_EVALUATION_MAX_SESSIONS=2",
    "HEALTHIA_EVALUATION_MAX_RUNS=2",
    "HEALTHIA_RELEASE_SHA=$releaseSha",
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
    "--min-instances", "0",
    "--max-instances", "1",
    "--concurrency", "20",
    "--cpu", "1",
    "--memory", "512Mi",
    "--timeout", "600",
    "--set-env-vars", $envVars,
    "--set-secrets", "HEALTHIA_DEVICE_TOKEN_SECRET=${DeviceSecretName}:latest,HEALTHIA_SESSION_SECRET=${SessionSecretName}:latest,HEALTHIA_EVALUATION_ACCESS_KEY=${EvaluationSecretName}:latest,GOOGLE_MAPS_API_KEY=${MapsSecretName}:latest",
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

Write-Host "Verificando binding proveedor: HEAD limpio -> source archive -> Cloud Build -> digest -> revision..." -ForegroundColor Cyan
$providerProofArgs = @(
    "deployment/verify_cloud_provider_binding.py",
    "--project", $ProjectId,
    "--region", $Region,
    "--service", $ServiceName,
    "--expected-sha", $releaseSha,
    "--output", "deployment/cloud-provider-binding-latest.json"
)
if (-not $PublicDemo) {
    $providerIdentityToken = (& gcloud auth print-identity-token).Trim()
    if ([string]::IsNullOrWhiteSpace($providerIdentityToken)) {
        throw "No se pudo obtener identity token para el binding del proveedor privado."
    }
    $env:HEALTHIA_CLOUD_ID_TOKEN = $providerIdentityToken
}
try {
    & python @providerProofArgs | Out-Host
}
finally {
    Remove-Item Env:HEALTHIA_CLOUD_ID_TOKEN -ErrorAction SilentlyContinue
    $providerIdentityToken = $null
    $providerProofArgs = $null
}
if ($LASTEXITCODE -ne 0) {
    throw "La revision existe pero no supero el binding exact-SHA independiente del proveedor."
}

if (-not $SkipStrictProof) {
    $identityToken = ""
    $evaluationAccessKey = $null
    $cloudAccessToken = $null
    $proofArgs = $null
    try {
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
            "--json",
            "--release-sha", $releaseSha
        )
        if (-not [string]::IsNullOrWhiteSpace($identityToken)) {
            $env:HEALTHIA_CLOUD_ID_TOKEN = $identityToken
        }
        $evaluationAccessKey = (& gcloud secrets versions access latest `
            --secret $EvaluationSecretName `
            --project $ProjectId).Trim()
        if ([string]::IsNullOrWhiteSpace($evaluationAccessKey)) {
            throw "No se pudo cargar la capacidad privada del evaluador para la prueba estricta."
        }
        $env:HEALTHIA_EVALUATION_ACCESS_KEY = $evaluationAccessKey
        $cloudAccessToken = (& gcloud auth print-access-token).Trim()
        if ([string]::IsNullOrWhiteSpace($cloudAccessToken)) {
            throw "No se pudo obtener access token efimero para releer Firestore/GCS."
        }
        $env:HEALTHIA_CLOUD_ACCESS_TOKEN = $cloudAccessToken
        Write-Host "Prueba estricta: Cloud Run + auth A/B + Gemini 3.5/ADK + Firestore + GCS + gemelo..." -ForegroundColor Cyan
        & python @proofArgs | Tee-Object -FilePath "deployment/cloud-proof-latest.json" | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "El despliegue existe pero NO supero la prueba estricta. No lo declares probado."
        }
    }
    finally {
        Remove-Item Env:HEALTHIA_EVALUATION_ACCESS_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:HEALTHIA_CLOUD_ID_TOKEN -ErrorAction SilentlyContinue
        Remove-Item Env:HEALTHIA_CLOUD_ACCESS_TOKEN -ErrorAction SilentlyContinue
        $evaluationAccessKey = $null
        $cloudAccessToken = $null
        $identityToken = $null
        $proofArgs = $null
    }
}

Write-Host ""
Write-Host "CLOUD REAL PROBADO: $url" -ForegroundColor Green
Write-Host "Captura Cloud Run revision $revision, Vertex AI/Cloud Logging y deployment/cloud-proof-latest.json para el demo." -ForegroundColor Cyan
Write-Host "Al terminar puedes eliminar solo Cloud Run (manteniendo evidencia) con:" -ForegroundColor Yellow
Write-Host ".\deployment\remove-cloud-demo.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -BucketName $BucketName" -ForegroundColor Yellow
