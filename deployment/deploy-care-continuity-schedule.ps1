param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [Parameter(Mandatory = $true)] [string] $SchedulerLocation,
    [string] $Region = "us-central1",
    [string] $ServiceName = "healthia-one-autopilot",
    [string] $SchedulerServiceAccount = "",
    [string] $JobName = "healthia-care-continuity-daily",
    [string] $Schedule = "0 12 * * *",
    [string] $TimeZone = "Etc/UTC",
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

if ([string]::IsNullOrWhiteSpace($SchedulerServiceAccount)) {
    throw "-SchedulerServiceAccount is required. This script will not create or guess an identity."
}
if (-not $Confirmed) {
    Write-Host "HEALTHIA_CARE_CONTINUITY_SCHEDULE_NOT_CONFIRMED"
    Write-Host "No Cloud Scheduler job or IAM mutation was created."
    exit 0
}

$requiredApis = @("run.googleapis.com", "cloudscheduler.googleapis.com")
$enabled = @(gcloud services list --project $ProjectId --enabled --format="value(config.name)")
foreach ($api in $requiredApis) {
    if ($enabled -notcontains $api) {
        throw "Required API is not enabled: $api. This script will not enable APIs silently."
    }
}

$schedulerEmail = if ($SchedulerServiceAccount -match "@") {
    $SchedulerServiceAccount
} else {
    "$SchedulerServiceAccount@$ProjectId.iam.gserviceaccount.com"
}

& gcloud iam service-accounts describe $schedulerEmail --project $ProjectId --format="value(email)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Scheduler service account not found or inaccessible: $schedulerEmail"
}

$serviceUrl = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serviceUrl)) {
    throw "Private autopilot Cloud Run service not found: $ServiceName"
}

Run-Gcloud @(
    "run", "services", "add-iam-policy-binding", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--member", "serviceAccount:$schedulerEmail",
    "--role", "roles/run.invoker"
)

$existing = gcloud scheduler jobs describe $JobName --project $ProjectId --location $SchedulerLocation --format="value(name)" 2>$null
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($existing)) {
    throw "Cloud Scheduler job '$JobName' already exists. Inspect or update it explicitly; this script will not mutate an existing schedule silently."
}

$target = "$serviceUrl/scheduled/care"
Run-Gcloud @(
    "scheduler", "jobs", "create", "http", $JobName,
    "--project", $ProjectId,
    "--location", $SchedulerLocation,
    "--schedule", $Schedule,
    "--time-zone", $TimeZone,
    "--uri", $target,
    "--http-method", "POST",
    "--oidc-service-account-email", $schedulerEmail,
    "--oidc-token-audience", $serviceUrl,
    "--attempt-deadline", "120s",
    "--max-retry-attempts", "2",
    "--min-backoff", "30s",
    "--max-backoff", "300s",
    "--description", "HealthIA daily zero-model appointment preparation reconciliation; patient-level execution remains consent-gated"
)

Write-Host "HEALTHIA_CARE_CONTINUITY_SCHEDULE_CREATED"
Write-Host "Care continuity: $JobName -> $Schedule ($TimeZone)"
Write-Host "Target: $target"
Write-Host "The job only wakes the private worker. Appointment Guardian remains patient-consent gated and stages external notifications only after durable state commit."
