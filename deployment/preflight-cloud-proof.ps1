param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$TopicName = "healthia-agentic-events",
    [string]$SubscriptionName = "healthia-agentic-events-push",
    [string]$SchedulerName = "healthia-agentic-tick",
    [string]$ResultBucketName = "",
    [switch]$RequirePatientAuth
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud CLI no esta instalado o no esta en PATH." }
if ([string]::IsNullOrWhiteSpace($ResultBucketName)) { $ResultBucketName = "$ProjectId-healthia-results" }
$ResultBucketName = $ResultBucketName.ToLowerInvariant()
$bucketUri = "gs://$ResultBucketName"
$checks = [ordered]@{}

function Read-GcloudJson {
    param([string[]]$Arguments)
    $raw = & gcloud @Arguments --format=json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { throw "No se pudo leer: gcloud $($Arguments -join ' ')" }
    return ($raw | ConvertFrom-Json)
}

function Add-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    $checks[$Name] = [ordered]@{ passed = $Passed; detail = $Detail }
    if ($Passed) { Write-Host "PASS  $Name" -ForegroundColor Green }
    else { Write-Host "FAIL  $Name :: $Detail" -ForegroundColor Red }
}

$account = (& gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null | Select-Object -First 1).Trim()
Add-Check "authenticated_gcloud" (-not [string]::IsNullOrWhiteSpace($account)) $(if ($account) { "active account available" } else { "no active gcloud account" })

$billing = Read-GcloudJson @("billing", "projects", "describe", $ProjectId)
Add-Check "billing_enabled" ([bool]$billing.billingEnabled) "billingEnabled=$($billing.billingEnabled)"

$service = Read-GcloudJson @("run", "services", "describe", $ServiceName, "--project", $ProjectId, "--region", $Region)
$url = [string]$service.status.url
$revision = [string]$service.status.latestReadyRevisionName
$annotations = $service.spec.template.metadata.annotations
$minScale = [string]$annotations.'autoscaling.knative.dev/minScale'
$maxScale = [string]$annotations.'autoscaling.knative.dev/maxScale'
if ([string]::IsNullOrWhiteSpace($minScale)) { $minScale = "0" }
Add-Check "cloud_run_ready" (-not [string]::IsNullOrWhiteSpace($url) -and -not [string]::IsNullOrWhiteSpace($revision)) "revision=$revision"
Add-Check "cloud_run_scale_to_zero" ($minScale -eq "0") "minScale=$minScale"
Add-Check "cloud_run_bounded_max" ($maxScale -eq "1") "maxScale=$maxScale"

$containers = @($service.spec.template.spec.containers)
$env = @{}
foreach ($container in $containers) {
    foreach ($entry in @($container.env)) {
        if ($entry.name -and $entry.value) { $env[[string]$entry.name] = [string]$entry.value }
    }
}
Add-Check "event_driven_agents" ($env["HEALTHIA_PROACTIVE_ENABLED"] -eq "false" -and $env["HEALTHIA_EVENT_DISPATCH_BACKEND"] -eq "pubsub") "proactive=$($env['HEALTHIA_PROACTIVE_ENABLED']) dispatch=$($env['HEALTHIA_EVENT_DISPATCH_BACKEND'])"
Add-Check "firestore_state" ($env["HEALTHIA_STORE_BACKEND"] -eq "firestore") "store=$($env['HEALTHIA_STORE_BACKEND'])"
Add-Check "private_result_backend" ($env["HEALTHIA_BLOB_BACKEND"] -eq "gcs" -and $env["HEALTHIA_RESULT_BUCKET"] -eq $ResultBucketName) "blob=$($env['HEALTHIA_BLOB_BACKEND']) bucket=$($env['HEALTHIA_RESULT_BUCKET'])"
if ($RequirePatientAuth) {
    Add-Check "patient_auth_required" ($env["HEALTHIA_AUTH_MODE"] -eq "identity_platform") "auth=$($env['HEALTHIA_AUTH_MODE'])"
}

$database = Read-GcloudJson @("firestore", "databases", "describe", "--database=(default)", "--project", $ProjectId)
Add-Check "firestore_ready" (-not [string]::IsNullOrWhiteSpace([string]$database.name)) "database=(default)"

$topic = Read-GcloudJson @("pubsub", "topics", "describe", $TopicName, "--project", $ProjectId)
Add-Check "pubsub_topic_ready" (-not [string]::IsNullOrWhiteSpace([string]$topic.name)) "topic=$TopicName"

$subscription = Read-GcloudJson @("pubsub", "subscriptions", "describe", $SubscriptionName, "--project", $ProjectId)
$pushEndpoint = [string]$subscription.pushConfig.pushEndpoint
$pushServiceAccount = [string]$subscription.pushConfig.oidcToken.serviceAccountEmail
Add-Check "pubsub_authenticated_push" ($pushEndpoint -eq "$url/api/internal/pubsub/mission" -and -not [string]::IsNullOrWhiteSpace($pushServiceAccount)) "endpoint=$pushEndpoint"

$schedulerRaw = & gcloud scheduler jobs describe $SchedulerName --location $Region --project $ProjectId --format=json 2>$null
if ($LASTEXITCODE -eq 0 -and $schedulerRaw) {
    $scheduler = $schedulerRaw | ConvertFrom-Json
    Add-Check "scheduler_paused" ([string]$scheduler.state -eq "PAUSED") "state=$($scheduler.state)"
} else {
    Add-Check "scheduler_paused" $true "scheduler absent; no periodic spend"
}

$bucket = Read-GcloudJson @("storage", "buckets", "describe", $bucketUri, "--project", $ProjectId)
$pap = [string]$bucket.iamConfiguration.publicAccessPrevention
$uniform = [bool]$bucket.iamConfiguration.uniformBucketLevelAccess.enabled
Add-Check "bucket_public_access_prevention" ($pap -eq "enforced") "publicAccessPrevention=$pap"
Add-Check "bucket_uniform_access" $uniform "uniformBucketLevelAccess=$uniform"
$iamRaw = & gcloud storage buckets get-iam-policy $bucketUri --format=json 2>$null
if ($LASTEXITCODE -ne 0 -or -not $iamRaw) { throw "No se pudo leer IAM del bucket." }
$iam = $iamRaw | ConvertFrom-Json
$publicMembers = @()
foreach ($binding in @($iam.bindings)) {
    foreach ($member in @($binding.members)) {
        if ($member -in @("allUsers", "allAuthenticatedUsers")) { $publicMembers += $member }
    }
}
Add-Check "bucket_not_public" ($publicMembers.Count -eq 0) $(if ($publicMembers.Count -eq 0) { "no public principals" } else { $publicMembers -join "," })

$failed = @($checks.GetEnumerator() | Where-Object { -not $_.Value.passed })
$result = [ordered]@{
    status = $(if ($failed.Count -eq 0) { "PASS" } else { "FAIL" })
    project_id = $ProjectId
    region = $Region
    service = $ServiceName
    service_url = $url
    revision = $revision
    checked_at_utc = [DateTime]::UtcNow.ToString("o")
    checks = $checks
    truth_boundary = "Read-only infrastructure preflight. It does not prove a live Gemini/ADK mission until capture-cloud-proof.ps1 records one."
}

New-Item -ItemType Directory -Path "dist/cloud-proof" -Force | Out-Null
$result | ConvertTo-Json -Depth 8 | Set-Content -Path "dist/cloud-proof/preflight.json" -Encoding utf8
$result | ConvertTo-Json -Depth 8
if ($failed.Count -gt 0) { exit 1 }
