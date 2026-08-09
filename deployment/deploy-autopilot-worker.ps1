param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [Parameter(Mandatory = $true)] [string] $Image,
    [Parameter(Mandatory = $true)] [string] $TriggerLocation,
    [string] $Region = "us-central1",
    [string] $ServiceName = "healthia-one-autopilot",
    [string] $TriggerName = "healthia-opportunity-events",
    [string] $RuntimeServiceAccount = "",
    [string] $EventarcServiceAccount = "",
    [switch] $Confirmed
)

$ErrorActionPreference = "Stop"

function Require-Command([string] $Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Run-Gcloud([string[]] $Arguments) {
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed: gcloud $($Arguments -join ' ')"
    }
}

Require-Command "gcloud"

if ([string]::IsNullOrWhiteSpace($RuntimeServiceAccount)) {
    throw "-RuntimeServiceAccount is required. Reuse a least-privilege HealthIA runtime identity; this script will not invent one."
}
if ([string]::IsNullOrWhiteSpace($EventarcServiceAccount)) {
    throw "-EventarcServiceAccount is required. It must be a user-managed identity for Eventarc invocation."
}
if (-not $Confirmed) {
    Write-Host "HEALTHIA_AUTOPILOT_DEPLOYMENT_NOT_CONFIRMED"
    Write-Host "No Cloud mutation was performed. Re-run with -Confirmed after reviewing project, image, identities and Firestore/Eventarc location."
    exit 0
}

$requiredApis = @(
    "run.googleapis.com",
    "firestore.googleapis.com",
    "eventarc.googleapis.com",
    "eventarcpublishing.googleapis.com",
    "logging.googleapis.com"
)
$enabled = @(gcloud services list --project $ProjectId --enabled --format="value(config.name)")
foreach ($api in $requiredApis) {
    if ($enabled -notcontains $api) {
        throw "Required API is not enabled: $api. This script fails closed and will not enable APIs silently."
    }
}

$runtimeEmail = if ($RuntimeServiceAccount -match "@") { $RuntimeServiceAccount } else { "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com" }
$eventarcEmail = if ($EventarcServiceAccount -match "@") { $EventarcServiceAccount } else { "$EventarcServiceAccount@$ProjectId.iam.gserviceaccount.com" }

foreach ($email in @($runtimeEmail, $eventarcEmail)) {
    & gcloud iam service-accounts describe $email --project $ProjectId --format="value(email)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Service account not found or inaccessible: $email" }
}

Write-Host "Deploying a PRIVATE Cloud Run worker. No --allow-unauthenticated flag will be used."
Run-Gcloud @(
    "run", "deploy", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--image", $Image,
    "--service-account", $runtimeEmail,
    "--no-allow-unauthenticated",
    "--min", "0",
    "--max", "1",
    "--concurrency", "1",
    "--memory", "512Mi",
    "--cpu", "1",
    "--command", "uvicorn",
    "--args", "healthia_one.autopilot_worker:app,--host,0.0.0.0,--port,8080",
    "--set-env-vars", "HEALTHIA_ENV=cloud,HEALTHIA_STORE_BACKEND=firestore,HEALTHIA_LLM_BACKEND=gemini_api,HEALTHIA_COST_MODE=guarded"
)

Run-Gcloud @(
    "run", "services", "add-iam-policy-binding", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--member", "serviceAccount:$eventarcEmail",
    "--role", "roles/run.invoker"
)

$existingTrigger = gcloud eventarc triggers describe $TriggerName --project $ProjectId --location $TriggerLocation --format="value(name)" 2>$null
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($existingTrigger)) {
    throw "Eventarc trigger '$TriggerName' already exists. Filters are immutable; inspect/delete it explicitly instead of mutating it silently."
}

Run-Gcloud @(
    "eventarc", "triggers", "create", $TriggerName,
    "--project", $ProjectId,
    "--location", $TriggerLocation,
    "--destination-run-service", $ServiceName,
    "--destination-run-region", $Region,
    "--destination-run-path", "/events/firestore",
    "--event-filters", "type=google.cloud.firestore.document.v1.created",
    "--event-filters", "database=(default)",
    "--event-filters-path-pattern", "document=healthia_autopilot_events/{eventId}",
    "--event-data-content-type", "application/protobuf",
    "--service-account", $eventarcEmail
)

Write-Host "HEALTHIA_AUTOPILOT_WORKER_DEPLOYED"
Write-Host "Cloud Run service: $ServiceName ($Region)"
Write-Host "Eventarc trigger: $TriggerName ($TriggerLocation)"
Write-Host "Document path: healthia_autopilot_events/{eventId}"
Write-Host "The worker remains private; Eventarc invokes it through IAM."
