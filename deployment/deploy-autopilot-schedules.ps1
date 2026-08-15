param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [Parameter(Mandatory = $true)] [string] $SchedulerLocation,
    [string] $Region = "us-central1",
    [string] $ServiceName = "healthia-one-autopilot",
    [string] $SchedulerServiceAccount = "",
    [string] $ScientificJobName = "healthia-scientific-radar-weekly",
    [string] $ResourceJobName = "healthia-resource-radar-monthly",
    [string] $RecoveryJobName = "healthia-autopilot-intent-recovery",
    [string] $ScientificSchedule = "0 10 * * 0",
    [string] $ResourceSchedule = "0 11 1 * *",
    [string] $RecoverySchedule = "*/15 * * * *",
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
    Write-Host "HEALTHIA_AUTOPILOT_SCHEDULES_NOT_CONFIRMED"
    Write-Host "No Cloud Scheduler jobs or IAM mutations were created."
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

$jobs = @(
    @{
        Name = $ScientificJobName
        Schedule = $ScientificSchedule
        Path = "/scheduled/scientific"
        Description = "HealthIA weekly scientific radar producer; patient-level execution remains opt-in"
    },
    @{
        Name = $ResourceJobName
        Schedule = $ResourceSchedule
        Path = "/scheduled/resources"
        Description = "HealthIA monthly assistance radar producer; patient-level execution remains opt-in and cost-guarded"
    },
    @{
        Name = $RecoveryJobName
        Schedule = $RecoverySchedule
        Path = "/scheduled/recover-intents"
        Description = "HealthIA recovery producer for already-authorized durable event intents left pending after process failure; zero model calls"
    }
)

foreach ($job in $jobs) {
    $existing = gcloud scheduler jobs describe $job.Name --project $ProjectId --location $SchedulerLocation --format="value(name)" 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($existing)) {
        throw "Cloud Scheduler job '$($job.Name)' already exists. Inspect/update it explicitly instead of mutating schedules silently."
    }

    $target = "$serviceUrl$($job.Path)"
    Run-Gcloud @(
        "scheduler", "jobs", "create", "http", $job.Name,
        "--project", $ProjectId,
        "--location", $SchedulerLocation,
        "--schedule", $job.Schedule,
        "--time-zone", $TimeZone,
        "--uri", $target,
        "--http-method", "POST",
        "--oidc-service-account-email", $schedulerEmail,
        "--oidc-token-audience", $serviceUrl,
        "--attempt-deadline", "120s",
        "--max-retry-attempts", "2",
        "--min-backoff", "30s",
        "--max-backoff", "300s",
        "--description", $job.Description
    )
}

Write-Host "HEALTHIA_AUTOPILOT_SCHEDULES_CREATED"
Write-Host "Scientific: $ScientificJobName -> $ScientificSchedule ($TimeZone)"
Write-Host "Resources: $ResourceJobName -> $ResourceSchedule ($TimeZone)"
Write-Host "Recovery: $RecoveryJobName -> $RecoverySchedule ($TimeZone)"
Write-Host "All jobs target a private Cloud Run service using OIDC. Radar permissions remain OFF by default; recovery only flushes previously staged authorized intents."
