param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [Parameter(Mandatory = $true)] [string] $OAuthClientSecretResource,
    [Parameter(Mandatory = $true)] [string] $OAuthStateSecretResource,
    [Parameter(Mandatory = $true)] [string] $RedirectUri,
    [string] $ServiceName = "healthia-one-demo",
    [string] $Region = "us-central1",
    [string] $PatientId = "",
    [switch] $Confirmed
)

$ErrorActionPreference = "Stop"

function Require-Command([string] $Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Run-Gcloud([string[]] $Arguments) {
    & $GcloudCommand @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed without exposing secret payloads: gcloud $($Arguments -join ' ')"
    }
}

function Parse-SecretVersionResource([string] $Resource, [string] $Label) {
    $pattern = "^projects/([^/]+)/secrets/([^/]+)/versions/([^/]+)$"
    $match = [regex]::Match($Resource, $pattern)
    if (-not $match.Success) {
        throw "$Label must be a full Secret Manager version resource: projects/PROJECT/secrets/SECRET/versions/VERSION"
    }
    if ($match.Groups[1].Value -ne $ProjectId) {
        throw "$Label must belong to ProjectId $ProjectId"
    }
    return @{
        Project = $match.Groups[1].Value
        Secret = $match.Groups[2].Value
        Version = $match.Groups[3].Value
    }
}

function Add-SecretRole([string] $SecretName, [string] $RuntimeEmail, [string] $Role) {
    Run-Gcloud @(
        "secrets", "add-iam-policy-binding", $SecretName,
        "--project", $ProjectId,
        "--member", "serviceAccount:$RuntimeEmail",
        "--role", $Role,
        "--quiet"
    )
}

function Patient-SecretId([string] $Value) {
    if (-not $Value.StartsWith("patient_")) {
        throw "PatientId must be a HealthIA patient_ identifier"
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha256.ComputeHash($bytes)
    } finally {
        $sha256.Dispose()
    }
    $hex = ([System.BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    return "healthia-google-oauth-$($hex.Substring(0, 24))"
}

Require-Command "gcloud"
$gcloudCmd = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue
$GcloudCommand = if ($gcloudCmd) { $gcloudCmd.Source } else { "gcloud" }
$clientSecret = Parse-SecretVersionResource $OAuthClientSecretResource "OAuthClientSecretResource"
$stateSecret = Parse-SecretVersionResource $OAuthStateSecretResource "OAuthStateSecretResource"

if ($ServiceName -ne "healthia-one-web-demo") {
    throw "ServiceName must be the isolated healthia-one-web-demo service; refusing to inject patient OAuth configuration into any other runtime"
}
if ($clientSecret.Secret -ne "healthia-google-oauth-client") {
    throw "OAuthClientSecretResource must reference healthia-google-oauth-client"
}
if ($stateSecret.Secret -ne "healthia-google-oauth-state") {
    throw "OAuthStateSecretResource must reference healthia-google-oauth-state"
}

$redirect = $null
if (-not [uri]::TryCreate($RedirectUri, [System.UriKind]::Absolute, [ref] $redirect)) {
    throw "RedirectUri must be an absolute URI"
}
if ($redirect.Scheme -ne "https") {
    throw "RedirectUri must use HTTPS for Cloud Run"
}
if ($redirect.AbsolutePath -ne "/api/google-constellation/oauth/callback") {
    throw "RedirectUri path must be /api/google-constellation/oauth/callback"
}

if (-not $Confirmed) {
    Write-Host "HEALTHIA_GOOGLE_OAUTH_NOT_CONFIRMED"
    Write-Host "No IAM, Secret Manager or Cloud Run mutation was performed."
    Write-Host "Required existing resources: OAuth client JSON secret version + OAuth state secret version."
    if ($PatientId) {
        Write-Host "A patient token-secret shell would be provisioned only after -Confirmed."
    }
    exit 0
}

$enabled = @(& $GcloudCommand services list --project $ProjectId --enabled --format="value(config.name)")
foreach ($api in @("run.googleapis.com", "secretmanager.googleapis.com")) {
    if ($enabled -notcontains $api) {
        throw "Required API is not enabled: $api. This script will not enable APIs silently."
    }
}

Run-Gcloud @("run", "services", "describe", $ServiceName, "--project", $ProjectId, "--region", $Region, "--format=value(metadata.name)")
$runtimeEmail = & $GcloudCommand run services describe $ServiceName --project $ProjectId --region $Region --format="value(spec.template.spec.serviceAccountName)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($runtimeEmail)) {
    throw "Unable to resolve the Cloud Run runtime service account"
}

foreach ($secret in @($clientSecret, $stateSecret)) {
    Run-Gcloud @(
        "secrets", "versions", "describe", $secret.Version,
        "--secret", $secret.Secret,
        "--project", $ProjectId,
        "--format=value(name)"
    )
    # Payload access is scoped to exactly the two application secrets.
    Add-SecretRole $secret.Secret $runtimeEmail "roles/secretmanager.secretAccessor"
}

$patientSecretName = ""
if (-not [string]::IsNullOrWhiteSpace($PatientId)) {
    $patientSecretName = Patient-SecretId $PatientId
    $secretNames = @(& $GcloudCommand secrets list --project $ProjectId --format="value(name)")
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to check whether the patient OAuth secret exists"
    }
    $existing = @($secretNames | Where-Object { $_ -eq $patientSecretName -or $_ -like "*/secrets/$patientSecretName" })
    if ($existing.Count -eq 0) {
        Run-Gcloud @(
            "secrets", "create", $patientSecretName,
            "--project", $ProjectId,
            "--replication-policy", "automatic",
            "--quiet"
        )
    }
    # The web runtime may add a refresh-token version and later read only this
    # patient's secret. Metadata Viewer is needed by the writer's existence check;
    # none of these roles permit access to unrelated project secrets.
    Add-SecretRole $patientSecretName $runtimeEmail "roles/secretmanager.secretVersionAdder"
    Add-SecretRole $patientSecretName $runtimeEmail "roles/secretmanager.secretAccessor"
    Add-SecretRole $patientSecretName $runtimeEmail "roles/secretmanager.viewer"
}

# App-client JSON remains an opaque Secret Manager resource reference. The state
# signing secret is injected directly as a Cloud Run secret environment variable.
Run-Gcloud @(
    "run", "services", "update", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--update-env-vars", "HEALTHIA_GOOGLE_OAUTH_CLIENT_SECRET_RESOURCE=$OAuthClientSecretResource,HEALTHIA_GOOGLE_OAUTH_REDIRECT_URI=$RedirectUri",
    "--update-secrets", "HEALTHIA_GOOGLE_OAUTH_STATE_SECRET=$($stateSecret.Secret):$($stateSecret.Version)",
    "--quiet"
)

$revision = & $GcloudCommand run services describe $ServiceName --project $ProjectId --region $Region --format="value(status.latestReadyRevisionName)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($revision)) {
    throw "OAuth configuration update completed but the ready Cloud Run revision could not be resolved"
}

Write-Host "HEALTHIA_GOOGLE_OAUTH_CONFIGURED"
Write-Host "Cloud Run service: $ServiceName"
Write-Host "Ready revision: $revision"
Write-Host "Redirect URI: $RedirectUri"
Write-Host "OAuth client payload: not displayed"
Write-Host "OAuth state payload: not displayed"
if ($patientSecretName) {
    Write-Host "Patient OAuth token secret shell: $patientSecretName (contains no token until patient consent callback succeeds)"
} else {
    Write-Host "Patient token secret not provisioned. Run this script again with -PatientId before that patient completes Google consent."
}
Write-Host "This script does not create a Google OAuth Client ID, register redirect URIs in Google Auth Platform, enable APIs, or grant project-wide Secret Manager access."
