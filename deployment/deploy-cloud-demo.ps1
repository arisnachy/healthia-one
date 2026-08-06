param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$SecretName = "healthia-gemini-api-key",
    [ValidateRange(1, 25)][int]$RequestLimit = 20,
    [ValidateRange(64, 2048)][int]$MaxOutputTokens = 700,
    [switch]$PublicDemo
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI no esta instalado o no esta en PATH."
}

Write-Host "MODO DEMO CLOUD CONTROLADO" -ForegroundColor Cyan
Write-Host "Proyecto: $ProjectId" -ForegroundColor White
Write-Host "Servicio: $ServiceName" -ForegroundColor White
Write-Host "Region: $Region" -ForegroundColor White
Write-Host "Cloud Run: min 0, max 1, facturacion por solicitud." -ForegroundColor Green
Write-Host "Google AI: maximo $RequestLimit solicitudes por proceso y $MaxOutputTokens tokens de salida." -ForegroundColor Green
Write-Host "Aviso: el limite del proceso se reinicia si Cloud Run reinicia la instancia. Configura tambien Spend Caps/Budgets en Cloud Billing." -ForegroundColor Yellow

$confirmation = Read-Host "Escribe DEPLOY para continuar"
if ($confirmation -ne "DEPLOY") {
    throw "Despliegue cancelado."
}

& gcloud config set project $ProjectId | Out-Host
if ($LASTEXITCODE -ne 0) { throw "No se pudo seleccionar el proyecto." }

$envVars = @(
    "HEALTHIA_ENV=cloud",
    "HEALTHIA_LLM_BACKEND=gemini_api",
    "HEALTHIA_STORE_BACKEND=firestore",
    "HEALTHIA_COST_MODE=cloud_demo",
    "HEALTHIA_AI_REQUEST_LIMIT=$RequestLimit",
    "HEALTHIA_COST_GUARD_START_ENABLED=true",
    "HEALTHIA_COST_CONTROL_UI=false",
    "HEALTHIA_AI_MAX_OUTPUT_TOKENS=$MaxOutputTokens",
    "HEALTHIA_PROACTIVE_ENABLED=false"
) -join ","

$args = @(
    "run", "deploy", $ServiceName,
    "--source", ".",
    "--project", $ProjectId,
    "--region", $Region,
    "--min", "0",
    "--max", "1",
    "--concurrency", "20",
    "--cpu", "1",
    "--memory", "512Mi",
    "--timeout", "60",
    "--set-env-vars", $envVars,
    "--set-secrets", "GEMINI_API_KEY=${SecretName}:latest",
    "--quiet"
)

if ($PublicDemo) {
    $args += "--allow-unauthenticated"
} else {
    $args += "--no-allow-unauthenticated"
}

& gcloud @args | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Cloud Run no pudo desplegar HealthIA." }

$url = & gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)"
Write-Host "" 
Write-Host "Demo desplegada: $url" -ForegroundColor Green
Write-Host "Captura ahora Cloud Run, revision, logs, Firestore y la URL para el video." -ForegroundColor Cyan
Write-Host "Al terminar, elimina el servicio con:" -ForegroundColor Yellow
Write-Host ".\deployment\remove-cloud-demo.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName" -ForegroundColor Yellow
