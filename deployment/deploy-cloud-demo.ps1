param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$FirestoreLocation = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$SecretName = "healthia-gemini-api-key",
    [string]$TopicName = "healthia-agentic-events",
    [string]$SubscriptionName = "healthia-agentic-events-push",
    [string]$SchedulerName = "healthia-agentic-tick",
    [ValidateRange(6, 5000)][int]$RequestLimit = 500,
    [ValidateRange(64, 2048)][int]$MaxOutputTokens = 700,
    [ValidateRange(1, 49)][double]$BudgetTargetUsd = 45,
    [ValidateRange(2, 50)][double]$AbsoluteBudgetUsd = 50,
    [switch]$PublicDemo,
    [switch]$SkipScheduler,
    [switch]$EnablePatientAuth,
    [string]$FirebaseApiKey = "",
    [string]$FirebaseAuthDomain = "",
    [string]$FirebaseAppId = ""
)

$ErrorActionPreference = "Stop"
$RuntimeServiceAccountName = "healthia-runtime"
$PushServiceAccountName = "healthia-pubsub-push"
$RuntimeServiceAccount = "$RuntimeServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$PushServiceAccount = "$PushServiceAccountName@$ProjectId.iam.gserviceaccount.com"

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & gcloud @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "gcloud fallo: gcloud $($Arguments -join ' ')" }
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
            try { Invoke-Gcloud "secrets" "versions" "add" $SecretName "--data-file=$temp" "--project" $ProjectId "--quiet" }
            finally { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
        } finally {
            if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
            $plain = $null
        }
    }
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud CLI no esta instalado o no esta en PATH." }
if ($BudgetTargetUsd -ge $AbsoluteBudgetUsd) { throw "BudgetTargetUsd debe quedar por debajo del limite absoluto." }
if ($EnablePatientAuth -and ([string]::IsNullOrWhiteSpace($FirebaseApiKey) -or [string]::IsNullOrWhiteSpace($FirebaseAuthDomain) -or [string]::IsNullOrWhiteSpace($FirebaseAppId))) {
    throw "Para -EnablePatientAuth debes proporcionar FirebaseApiKey, FirebaseAuthDomain y FirebaseAppId desde la app web registrada en Identity Platform/Firebase."
}

Write-Host ""
Write-Host "HEALTHIA ONE · CLOUD AGENTIC DEMO" -ForegroundColor Cyan
Write-Host "Proyecto: $ProjectId" -ForegroundColor White
Write-Host "Region Cloud Run/PubSub: $Region" -ForegroundColor White
Write-Host "Runtime: Google ADK + Gemini + Pub/Sub + Firestore" -ForegroundColor White
Write-Host "Agentes: A DEMANDA. Los eventos sin trabajo util no llaman a Gemini." -ForegroundColor Green
Write-Host "Cloud Run: min=0, max=1, CPU por solicitud; Scheduler PAUSADO por defecto." -ForegroundColor Green
Write-Host "Presupuesto de trabajo: aviso/objetivo USD $BudgetTargetUsd; limite absoluto deseado USD $AbsoluteBudgetUsd." -ForegroundColor Yellow
Write-Host "IMPORTANTE: el corte monetario real debe configurarse en Cloud Billing Spend Caps/Budgets. El contador de $RequestLimit solicitudes es solo un fusible tecnico de emergencia por instancia." -ForegroundColor Yellow
Write-Host "Recomendacion: spend cap Gemini <= USD 25, Cloud Run <= USD 10 y presupuesto global del proyecto USD $BudgetTargetUsd, dejando margen para Firestore/otros cargos y latencia." -ForegroundColor Yellow
if ($EnablePatientAuth) { Write-Host "Identidad: Google Identity Platform/Firebase Auth (Google + email/password)." -ForegroundColor Green }
else { Write-Host "Identidad: desactivada para prueba infra estricta. Usa -EnablePatientAuth en la demo para jueces." -ForegroundColor DarkYellow }
if ($PublicDemo -and -not $EnablePatientAuth) { Write-Host "ADVERTENCIA: servicio publico sin identidad de paciente. Recomendado solo para una ventana de prueba muy corta." -ForegroundColor Red }

$budgetAck = Read-Host "Confirma que configuraste controles de Billing por debajo de USD $AbsoluteBudgetUsd escribiendo BUDGET"
if ($budgetAck -ne "BUDGET") { throw "Despliegue cancelado: primero configura el presupuesto/spend caps." }
$confirmation = Read-Host "Escribe DEPLOY para continuar"
if ($confirmation -ne "DEPLOY") { throw "Despliegue cancelado." }

Invoke-Gcloud "config" "set" "project" $ProjectId
$services = @(
    "run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com",
    "firestore.googleapis.com", "secretmanager.googleapis.com", "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com", "identitytoolkit.googleapis.com"
)
Invoke-Gcloud "services" "enable" @services "--project" $ProjectId

Ensure-ServiceAccount $RuntimeServiceAccountName "HealthIA ONE runtime"
Ensure-ServiceAccount $PushServiceAccountName "HealthIA PubSub push identity"
Ensure-SecretWithVersion
foreach ($role in @("roles/datastore.user", "roles/pubsub.publisher", "roles/logging.logWriter")) {
    Invoke-Gcloud "projects" "add-iam-policy-binding" $ProjectId "--member=serviceAccount:$RuntimeServiceAccount" "--role=$role" "--quiet"
}
Invoke-Gcloud "secrets" "add-iam-policy-binding" $SecretName "--project" $ProjectId "--member=serviceAccount:$RuntimeServiceAccount" "--role=roles/secretmanager.secretAccessor" "--quiet"

if (-not (Test-GcloudResource @("firestore", "databases", "describe", "--database=(default)", "--project", $ProjectId))) {
    Invoke-Gcloud "firestore" "databases" "create" "--database=(default)" "--location=$FirestoreLocation" "--type=firestore-native" "--project" $ProjectId "--quiet"
}
if (-not (Test-GcloudResource @("pubsub", "topics", "describe", $TopicName, "--project", $ProjectId))) {
    Invoke-Gcloud "pubsub" "topics" "create" $TopicName "--project" $ProjectId "--quiet"
}

$authMode = if ($EnablePatientAuth) { "identity_platform" } else { "local" }
$envItems = @(
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
    "HEALTHIA_CLOUD_BUDGET_TARGET_USD=$BudgetTargetUsd",
    "HEALTHIA_CLOUD_BUDGET_ABSOLUTE_USD=$AbsoluteBudgetUsd",
    "HEALTHIA_PROACTIVE_ENABLED=false",
    "HEALTHIA_MISSION_RUNTIME=adk",
    "HEALTHIA_AGENTIC_EVENTS_ENABLED=true",
    "HEALTHIA_EVENT_DISPATCH_BACKEND=pubsub",
    "HEALTHIA_PUBSUB_TOPIC=$TopicName",
    "HEALTHIA_CLOUD_REGION=$Region",
    "HEALTHIA_AUTH_MODE=$authMode"
)
if ($EnablePatientAuth) {
    $envItems += @(
        "HEALTHIA_FIREBASE_API_KEY=$FirebaseApiKey",
        "HEALTHIA_FIREBASE_AUTH_DOMAIN=$FirebaseAuthDomain",
        "HEALTHIA_FIREBASE_PROJECT_ID=$ProjectId",
        "HEALTHIA_FIREBASE_APP_ID=$FirebaseAppId"
    )
}
$envVars = $envItems -join ","

$deployArgs = @(
    "run", "deploy", $ServiceName, "--source", ".", "--project", $ProjectId, "--region", $Region,
    "--service-account", $RuntimeServiceAccount, "--min-instances", "0", "--max-instances", "1",
    "--concurrency", "8", "--cpu", "1", "--memory", "512Mi", "--timeout", "60", "--cpu-throttling",
    "--set-env-vars", $envVars, "--set-secrets", "GEMINI_API_KEY=${SecretName}:latest", "--quiet"
)
if ($PublicDemo) { $deployArgs += "--allow-unauthenticated" } else { $deployArgs += "--no-allow-unauthenticated" }
Invoke-Gcloud @deployArgs

$url = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)").Trim()
if (-not $url) { throw "Cloud Run no devolvio una URL." }
$revision = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.latestReadyRevisionName)").Trim()

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
    Invoke-Gcloud "scheduler" "jobs" "pause" $SchedulerName "--location=$Region" "--project" $ProjectId "--quiet"
}

Write-Host ""
Write-Host "DESPLIEGUE AGENTIC COMPLETADO" -ForegroundColor Green
Write-Host "Cloud Run URL: $url" -ForegroundColor Cyan
Write-Host "Revision: $revision" -ForegroundColor Cyan
Write-Host "Pub/Sub topic: $TopicName" -ForegroundColor Cyan
Write-Host "Fusible tecnico: $RequestLimit solicitudes por instancia; agentes a demanda." -ForegroundColor Cyan
Write-Host "Objetivo de Billing: USD $BudgetTargetUsd / limite deseado USD $AbsoluteBudgetUsd." -ForegroundColor Cyan
if (-not $SkipScheduler) { Write-Host "Scheduler: $SchedulerName (PAUSADO)." -ForegroundColor Cyan }
if ($EnablePatientAuth) { Write-Host "Login: Google + correo/contraseña habilitado. Añade $url a los dominios autorizados de Firebase/Identity Platform." -ForegroundColor Cyan }
Write-Host ""
Write-Host "Prueba infra estricta (puedes redesplegar con -RequestLimit 6 para reservar solo seis llamadas):" -ForegroundColor White
Write-Host ".\deployment\capture-cloud-proof.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -SchedulerName $SchedulerName" -ForegroundColor Yellow
Write-Host "Limpieza al terminar:" -ForegroundColor White
Write-Host ".\deployment\remove-cloud-demo.ps1 -ProjectId $ProjectId -Region $Region -ServiceName $ServiceName -TopicName $TopicName -SubscriptionName $SubscriptionName -SchedulerName $SchedulerName" -ForegroundColor Yellow
