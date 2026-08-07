param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$FirestoreLocation = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$SecretName = "healthia-gemini-api-key",
    [string]$TopicName = "healthia-agentic-events",
    [string]$SubscriptionName = "healthia-agentic-events-push",
    [string]$SchedulerName = "healthia-agentic-tick",
    [ValidateRange(2, 20)][int]$RequestLimit = 6,
    [ValidateRange(64, 1024)][int]$MaxOutputTokens = 350,
    [switch]$PublicDemo,
    [switch]$SkipScheduler
)

$ErrorActionPreference = "Stop"
$RuntimeServiceAccountName = "healthia-runtime"
$PushServiceAccountName = "healthia-pubsub-push"
$RuntimeServiceAccount = "$RuntimeServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$PushServiceAccount = "$PushServiceAccountName@$ProjectId.iam.gserviceaccount.com"

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & gcloud @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud fallo: gcloud $($Arguments -join ' ')"
    }
}

function Test-GcloudResource {
    param([string[]]$Arguments)
    & gcloud @Arguments *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-ServiceAccount {
    param([string]$Name, [string]$DisplayName)
    if (-not (Test-GcloudResource @("iam", "service-accounts", "describe", "$Name@$ProjectId.iam.gserviceaccount.com", "--project", $ProjectId))) {
        Invoke-Gcloud "iam" "service-accounts" "create" $Name "--display-name" $DisplayName "--project" $ProjectId "--quiet"
    }
}

function Ensure-SecretWithVersion {
    if (-not (Test-GcloudResource @("secrets", "describe", $SecretName, "--project", $ProjectId))) {
        Invoke-Gcloud "secrets" "create" $SecretName "--replication-policy=automatic" "--project" $ProjectId "--quiet"
        Write-Host "El secreto fue creado, pero aun no contiene la API key." -ForegroundColor Yellow
    }

    $versions = & gcloud secrets versions list $SecretName --project $ProjectId --filter="state=ENABLED" --format="value(name)" 2>$null
    if (-not $versions) {
        Write-Host "Introduce la Gemini API key. No se mostrara ni se guardara en el repositorio." -ForegroundColor Cyan
        $secure = Read-Host "Gemini API key" -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
            if ([string]::IsNullOrWhiteSpace($plain)) { throw "La API key esta vacia." }
            $temp = Join-Path ([IO.Path]::GetTempPath()) ("healthia-key-" + [guid]::NewGuid().ToString("N") + ".txt")
            [IO.File]::WriteAllText($temp, $plain, [Text.UTF8Encoding]::new($false))
            try {
                Invoke-Gcloud "secrets" "versions" "add" $SecretName "--data-file=$temp" "--project" $ProjectId "--quiet"
            } finally {
                Remove-Item $temp -Force -ErrorAction SilentlyContinue
            }
        } finally {
            if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
            $plain = $null
        }
    }
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI no esta instalado o no esta en PATH."
}

Write-Host "" 
Write-Host "HEALTHIA ONE · CLOUD AGENTIC DEMO" -ForegroundColor Cyan
Write-Host "Proyecto: $ProjectId" -ForegroundColor White
Write-Host "Region Cloud Run/PubSub: $Region" -ForegroundColor White
Write-Host "Firestore: $FirestoreLocation" -ForegroundColor White
Write-Host "Runtime: Google ADK + Gemini + Pub/Sub + Firestore" -ForegroundColor White
Write-Host "Costo: Cloud Run min=0/max=1, request-based CPU, scheduler PAUSADO por defecto." -ForegroundColor Green
Write-Host "IA: reserva conservadora de hasta 2 llamadas por mision ADK; techo del proceso=$RequestLimit." -ForegroundColor Green
Write-Host "No sustituye Budgets/Alerts de Cloud Billing. El techo del proceso se reinicia con una instancia nueva." -ForegroundColor Yellow
if ($PublicDemo) {
    Write-Host "ADVERTENCIA: -PublicDemo hace publica la UI/API. Para la evidencia cloud se recomienda mantener el servicio privado." -ForegroundColor Yellow
}

$confirmation = Read-Host "Escribe DEPLOY para continuar"
if ($confirmation -ne "DEPLOY") { throw "Despliegue cancelado." }

Invoke-Gcloud "config" "set" "project" $ProjectId

$services = @(
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com"
)
Invoke-Gcloud "services" "enable" @services "--project" $ProjectId

Ensure-ServiceAccount $RuntimeServiceAccountName "HealthIA ONE runtime"
Ensure-ServiceAccount $PushServiceAccountName "HealthIA PubSub push identity"
Ensure-SecretWithVersion

# Runtime least-privilege roles needed by the application.
foreach ($role in @("roles/datastore.user", "roles/pubsub.publisher", "roles/logging.logWriter")) {
    Invoke-Gcloud "projects" "add-iam-policy-binding" $ProjectId "--member=serviceAccount:$RuntimeServiceAccount" "--role=$role" "--quiet"
}
Invoke-Gcloud "secrets" "add-iam-policy-binding" $SecretName "--project" $ProjectId "--member=serviceAccount:$RuntimeServiceAccount" "--role=roles/secretmanager.secretAccessor" "--quiet"

# Firestore Native is created once. Do not delete it automatically during normal cleanup.
if (-not (Test-GcloudResource @("firestore", "databases", "describe", "--database=(default)", "--project", $ProjectId))) {
    Invoke-Gcloud "firestore" "databases" "create" "--database=(default)" "--location=$FirestoreLocation" "--type=firestore-native" "--project" $ProjectId "--quiet"
}

if (-not (Test-GcloudResource @("pubsub", "topics", "describe", $TopicName, "--project", $ProjectId))) {
    Invoke-Gcloud "pubsub" "topics" "create" $TopicName "--project" $ProjectId "--quiet"
}

$envVars = @(
    "GOOGLE_CLOUD_PROJECT=$ProjectId",
    "HEALTHIA_ENV=cloud",
    "HEALTHIA_MODEL=gemini-3.6-flash",
    "HEALTHIA_LLM_BACKEND=gemini_api",
    "HEALTHIA_STORE_BACKEND=firestore",
    "HEALTHIA_COST_MODE=cloud_demo",
    "HEALTHIA_AI_REQUEST_LIMIT=$RequestLimit",
    "HEALTHIA_COST_GUARD_START_ENABLED=true",
    "HEALTHIA_COST_CONTROL_UI=false",
    "HEALTHIA_AI_MAX_OUTPUT_TOKENS=$MaxOutputTokens",
    "HEALTHIA_PROACTIVE_ENABLED=false",
    "HEALTHIA_MISSION_RUNTIME=adk",
    "HEALTHIA_AGENTIC_EVENTS_ENABLED=true",
    "HEALTHIA_EVENT_DISPATCH_BACKEND=pubsub",
    "HEALTHIA_PUBSUB_TOPIC=$TopicName",
    "HEALTHIA_CLOUD_REGION=$Region"
) -join ","

$deployArgs = @(
    "run", "deploy", $ServiceName,
    "--source", ".",
    "--project", $ProjectId,
    "--region", $Region,
    "--service-account", $RuntimeServiceAccount,
    "--min-instances", "0",
    "--max-instances", "1",
    "--concurrency", "8",
    "--cpu", "1",
    "--memory", "512Mi",
    "--timeout", "60",
    "--cpu-throttling",
    "--set-env-vars", $envVars,
    "--set-secrets", "GEMINI_API_KEY=${SecretName}:latest",
    "--quiet"
)
if ($PublicDemo) { $deployArgs += "--allow-unauthenticated" } else { $deployArgs += "--no-allow-unauthenticated" }
Invoke-Gcloud @deployArgs

$url = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)").Trim()
if (-not $url) { throw "Cloud Run no devolvio una URL." }
$revision = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.latestReadyRevisionName)").Trim()

# Authenticated Pub/Sub push -> private Cloud Run endpoint.
Invoke-Gcloud "run" "services" "add-iam-policy-binding" $ServiceName "--project" $ProjectId "--region" $Region "--member=serviceAccount:$PushServiceAccount" "--role=roles/run.invoker" "--quiet"
$projectNumber = (& gcloud projects describe $ProjectId --format "value(projectNumber)").Trim()
if (-not $projectNumber) { throw "No se pudo resolver el numero del proyecto." }
$pubsubServiceAgent = "service-$projectNumber@gcp-sa-pubsub.iam.gserviceaccount.com"
Invoke-Gcloud "projects" "add-iam-policy-binding" $ProjectId "--member=serviceAccount:$pubsubServiceAgent" "--role=roles/iam.serviceAccountTokenCreator" "--quiet"

if (Test-GcloudResource @("pubsub", "subscriptions", "describe", $SubscriptionName, "--project", $ProjectId)) {
    Invoke-Gcloud "pubsub" "subscriptions" "modify-push-config" $SubscriptionName "--project" $ProjectId "--push-endpoint=$url/api/internal/pubsub/mission" "--push-auth-service-account=$PushServiceAccount" "--push-auth-token-audience=$url"
} else {
    Invoke-Gcloud "pubsub" "subscriptions" "create" $SubscriptionName "--project" $ProjectId "--topic=$TopicName" "--push-endpoint=$url/api/internal/pubsub/mission" "--push-auth-service-account=$PushServiceAccount" "--push-auth-token-audience=$url" "--ack-deadline=60" "--min-retry-delay=10s" "--max-retry-delay=60s" "--quiet"
}

if (-not $SkipScheduler) {
    $scheduledEvent = '{"event_type":"scheduled_tick","patient_id":"patient_demo","source_id":"cloud_scheduler","payload":{"reason":"periodic_continuity"}}'
    if (Test-GcloudResource @("scheduler", "jobs", "describe", $SchedulerName, "--location", $Region, "--project", $ProjectId)) {
        Invoke-Gcloud "scheduler" "jobs" "update" "pubsub" $SchedulerName "--location=$Region" "--project=$ProjectId" "--schedule=0 * * * *" "--topic=$TopicName" "--message-body=$scheduledEvent" "--max-retry-attempts=1" "--quiet"
    } else {
        Invoke-Gcloud "scheduler" "jobs" "create" "pubsub" $SchedulerName "--location=$Region" "--project=$ProjectId" "--schedule=0 * * * *" "--topic=$TopicName" "--message-body=$scheduledEvent" "--max-retry-attempts=1" "--quiet"
    }
    Invoke-Gcloud "scheduler" "jobs" "pause" $SchedulerName "--location=$Region" "--project=$ProjectId" "--quiet"
}

Write-Host ""
Write-Host "DESPLIEGUE AGENTIC COMPLETADO" -ForegroundColor Green
Write-Host "Cloud Run URL: $url" -ForegroundColor Cyan
Write-Host "Revision: $revision" -ForegroundColor Cyan
Write-Host "Pub/Sub topic: $TopicName" -ForegroundColor Cyan
Write-Host "Push subscription: $SubscriptionName -> /api/internal/pubsub/mission" -ForegroundColor Cyan
if (-not $SkipScheduler) { Write-Host "Scheduler: $SchedulerName (PAUSADO; ejecutar manualmente para evidencia)." -ForegroundColor Cyan }
Write-Host ""
Write-Host "Siguiente paso de evidencia real:" -ForegroundColor White
Write-Host ".\deployment\capture-cloud-proof.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -SchedulerName $SchedulerName" -ForegroundColor Yellow
Write-Host ""
Write-Host "Limpieza al terminar:" -ForegroundColor White
Write-Host ".\deployment\remove-cloud-demo.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -TopicName $TopicName -SubscriptionName $SubscriptionName -SchedulerName $SchedulerName" -ForegroundColor Yellow
