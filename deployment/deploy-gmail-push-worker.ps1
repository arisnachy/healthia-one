param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [Parameter(Mandatory = $true)] [string] $Image,
    [Parameter(Mandatory = $true)] [string] $RuntimeServiceAccount,
    [Parameter(Mandatory = $true)] [string] $PushInvokerServiceAccount,
    [Parameter(Mandatory = $true)] [string] $SchedulerServiceAccount,
    [Parameter(Mandatory = $true)] [string] $TopicName,
    [string] $Region = "us-central1",
    [string] $SchedulerLocation = "us-central1",
    [string] $ServiceName = "healthia-gmail-worker",
    [string] $SubscriptionName = "healthia-gmail-push",
    [string] $RenewJobName = "healthia-gmail-watch-renewal",
    [string] $RenewSchedule = "0 5 * * *",
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

function Resolve-ServiceAccount([string] $Value) {
    if ($Value -match "@") { return $Value }
    return "$Value@$ProjectId.iam.gserviceaccount.com"
}

Require-Command "gcloud"

$runtimeEmail = Resolve-ServiceAccount $RuntimeServiceAccount
$pushEmail = Resolve-ServiceAccount $PushInvokerServiceAccount
$schedulerEmail = Resolve-ServiceAccount $SchedulerServiceAccount
$fullTopic = if ($TopicName.StartsWith("projects/")) { $TopicName } else { "projects/$ProjectId/topics/$TopicName" }
$topicPrefix = "projects/$ProjectId/topics/"

if (-not $fullTopic.StartsWith($topicPrefix)) {
    throw "Gmail Pub/Sub topic must belong to ProjectId $ProjectId. Got: $fullTopic"
}

if (-not $Confirmed) {
    Write-Host "HEALTHIA_GMAIL_WORKER_NOT_CONFIRMED"
    Write-Host "No Cloud Run, Pub/Sub, Scheduler or IAM mutation was performed."
    exit 0
}

$requiredApis = @(
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudscheduler.googleapis.com"
)
$enabled = @(gcloud services list --project $ProjectId --enabled --format="value(config.name)")
foreach ($api in $requiredApis) {
    if ($enabled -notcontains $api) {
        throw "Required API is not enabled: $api. This script will not enable APIs silently."
    }
}

foreach ($email in @($runtimeEmail, $pushEmail, $schedulerEmail)) {
    & gcloud iam service-accounts describe $email --project $ProjectId --format="value(email)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Required service account not found or inaccessible: $email"
    }
}

& gcloud pubsub topics describe $fullTopic --project $ProjectId --format="value(name)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Required Gmail Pub/Sub topic does not exist: $fullTopic"
}

# Gmail API publishes mailbox notifications as this Google-managed identity.
# The binding is topic-scoped, not project-wide.
Run-Gcloud @(
    "pubsub", "topics", "add-iam-policy-binding", $fullTopic,
    "--project", $ProjectId,
    "--member", "serviceAccount:gmail-api-push@system.gserviceaccount.com",
    "--role", "roles/pubsub.publisher"
)

Write-Host "Deploying a PRIVATE Cloud Run Gmail worker."
Run-Gcloud @(
    "run", "deploy", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--image", $Image,
    "--service-account", $runtimeEmail,
    "--no-allow-unauthenticated",
    "--min-instances", "0",
    "--max-instances", "2",
    "--concurrency", "8",
    "--memory", "512Mi",
    "--cpu", "1",
    "--command", "uvicorn",
    "--args", "healthia_one.gmail_push_worker:app,--host,0.0.0.0,--port,8080",
    "--set-env-vars", "GOOGLE_CLOUD_PROJECT=$ProjectId,HEALTHIA_ENV=cloud,HEALTHIA_STORE_BACKEND=firestore,HEALTHIA_LLM_BACKEND=gemini_api,HEALTHIA_GMAIL_PUBSUB_TOPIC=$fullTopic"
)

$serviceUrl = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.url)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serviceUrl)) {
    throw "Unable to resolve deployed Gmail worker Cloud Run URL"
}

foreach ($invoker in @($pushEmail, $schedulerEmail)) {
    Run-Gcloud @(
        "run", "services", "add-iam-policy-binding", $ServiceName,
        "--project", $ProjectId,
        "--region", $Region,
        "--member", "serviceAccount:$invoker",
        "--role", "roles/run.invoker"
    )
}

$subscriptionNames = @(gcloud pubsub subscriptions list --project $ProjectId --format="value(name)")
$existingSubscription = @($subscriptionNames | Where-Object { $_ -eq $SubscriptionName -or $_ -eq "projects/$ProjectId/subscriptions/$SubscriptionName" })
if ($existingSubscription.Count -gt 0) {
    throw "Pub/Sub subscription '$SubscriptionName' already exists. Inspect/delete/update it explicitly instead of silently changing its authenticated push target."
}

Run-Gcloud @(
    "pubsub", "subscriptions", "create", $SubscriptionName,
    "--project", $ProjectId,
    "--topic", $fullTopic,
    "--push-endpoint", "$serviceUrl/events/gmail-push",
    "--push-auth-service-account", $pushEmail,
    "--push-auth-token-audience", $serviceUrl,
    "--ack-deadline", "30",
    "--message-retention-duration", "1d"
)

$jobNames = @(gcloud scheduler jobs list --project $ProjectId --location $SchedulerLocation --format="value(name)")
$existingJob = @($jobNames | Where-Object { $_ -eq $RenewJobName -or $_ -like "*/jobs/$RenewJobName" })
if ($existingJob.Count -gt 0) {
    throw "Cloud Scheduler job '$RenewJobName' already exists. Inspect/update it explicitly instead of silently changing renewal cadence."
}

Run-Gcloud @(
    "scheduler", "jobs", "create", "http", $RenewJobName,
    "--project", $ProjectId,
    "--location", $SchedulerLocation,
    "--schedule", $RenewSchedule,
    "--time-zone", $TimeZone,
    "--uri", "$serviceUrl/scheduled/renew-gmail-watches",
    "--http-method", "POST",
    "--oidc-service-account-email", $schedulerEmail,
    "--oidc-token-audience", $serviceUrl,
    "--attempt-deadline", "120s",
    "--max-retry-attempts", "2",
    "--min-backoff", "30s",
    "--max-backoff", "300s",
    "--description", "Renew expiring patient-authorized Gmail API watches; mailbox changes remain event-driven via Pub/Sub"
)

Write-Host "HEALTHIA_GMAIL_WORKER_DEPLOYED"
Write-Host "Cloud Run: $ServiceName -> $serviceUrl (private)"
Write-Host "Topic: $fullTopic"
Write-Host "Push subscription: $SubscriptionName -> /events/gmail-push"
Write-Host "Watch renewal: $RenewJobName -> $RenewSchedule ($TimeZone)"
Write-Host "Runtime identity must already have least-privilege Firestore/Secret Manager access; this script does not grant broad secret access."
