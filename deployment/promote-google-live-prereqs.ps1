param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [string] $Region = "us-central1",
    [string] $WebServiceName = "healthia-one-web-demo",
    [string] $MapsSecretName = "healthia-google-maps-api-key",
    [string] $MapsKeyDisplayName = "HealthIA ONE Places server",
    [switch] $Confirmed
)

$ErrorActionPreference = "Stop"

function Require-Command([string] $Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Invoke-Gcloud([string[]] $Arguments) {
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud command failed"
    }
}

Require-Command "gcloud"

Write-Host "KIRA Google live prerequisite promotion"
Write-Host "Project: $ProjectId"
Write-Host "Region: $Region"
Write-Host "Public web service only: $WebServiceName"
Write-Host "Private backend healthia-one-demo is not modified by this script."

if (-not $Confirmed) {
    Write-Host "HEALTHIA_GOOGLE_LIVE_PREREQS_NOT_CONFIRMED"
    Write-Host "Planned mutations: enable Calendar/Tasks/Places/API Keys; create a Places-only server key if needed; store it in Secret Manager; grant only the web runtime access to that secret; make only the isolated web demo publicly reachable; verify app-session 401 boundaries."
    exit 0
}

$requiredApis = @(
    "calendar-json.googleapis.com",
    "tasks.googleapis.com",
    "places.googleapis.com",
    "apikeys.googleapis.com"
)

foreach ($api in $requiredApis) {
    Write-Host "Ensuring API: $api"
    Invoke-Gcloud @("services", "enable", $api, "--project", $ProjectId, "--quiet")
}

$serviceUrl = (& gcloud run services describe $WebServiceName --project $ProjectId --region $Region --format="value(status.url)").Trim()
$runtimeEmail = (& gcloud run services describe $WebServiceName --project $ProjectId --region $Region --format="value(spec.template.spec.serviceAccountName)").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serviceUrl) -or [string]::IsNullOrWhiteSpace($runtimeEmail)) {
    throw "The isolated HealthIA ONE web service does not exist or has no runtime identity. Run the repository public-web preparation first."
}

# Make only the isolated patient-facing web service reachable. HealthIA's own
# session middleware still protects patient APIs. The private worker/backend is
# intentionally not changed.
Invoke-Gcloud @("run", "services", "update", $WebServiceName, "--project", $ProjectId, "--region", $Region, "--no-invoker-iam-check", "--quiet")

# Find or create one server-side API key restricted to Places API (New). The key
# string is captured only in process memory and piped directly into Secret
# Manager; it is never printed, committed, or sent to the browser.
$keyResource = (& gcloud services api-keys list --project $ProjectId --filter="displayName='$MapsKeyDisplayName'" --limit=1 --format="value(name)").Trim()
if ([string]::IsNullOrWhiteSpace($keyResource)) {
    $keyResource = (& gcloud services api-keys create `
        --project $ProjectId `
        --display-name $MapsKeyDisplayName `
        --api-target="service=places.googleapis.com" `
        --format="value(name)" `
        --quiet).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($keyResource)) {
        throw "Unable to create the restricted Places API key"
    }
}

$mapsKey = (& gcloud services api-keys get-key-string $keyResource --project $ProjectId --format="value(keyString)").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mapsKey)) {
    throw "Unable to retrieve the Places API key string"
}

$secretExists = & gcloud secrets describe $MapsSecretName --project $ProjectId --format="value(name)" 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string] $secretExists)) {
    Invoke-Gcloud @("secrets", "create", $MapsSecretName, "--project", $ProjectId, "--replication-policy", "automatic", "--quiet")
}

try {
    $mapsVersion = $mapsKey | & gcloud secrets versions add $MapsSecretName `
        --project $ProjectId `
        --data-file=- `
        --format="value(name)" `
        --quiet
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string] $mapsVersion)) {
        throw "Secret Manager did not return a Places key version"
    }
} finally {
    $mapsKey = $null
}

# The server-side Places key is readable only by the exact Cloud Run runtime
# identity. Do not grant project-wide Secret Manager roles for this key.
Invoke-Gcloud @(
    "secrets", "add-iam-policy-binding", $MapsSecretName,
    "--project", $ProjectId,
    "--member", "serviceAccount:$runtimeEmail",
    "--role", "roles/secretmanager.secretAccessor",
    "--quiet"
)

Invoke-Gcloud @(
    "run", "services", "update", $WebServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--update-secrets", "GOOGLE_MAPS_API_KEY=${MapsSecretName}:latest",
    "--quiet"
)

function Probe([string] $Path) {
    try {
        $response = Invoke-WebRequest -Uri ($serviceUrl.TrimEnd('/') + $Path) -MaximumRedirection 0 -SkipHttpErrorCheck -TimeoutSec 15
        return [int] $response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int] $_.Exception.Response.StatusCode
        }
        return 0
    }
}

$health = Probe "/healthz"
$login = Probe "/login"
$session = Probe "/api/auth/session"
$bootstrap = Probe "/api/bootstrap"
$opportunities = Probe "/api/opportunities"
$googleCaps = Probe "/api/google-constellation/capabilities"
$oauthReadiness = Probe "/api/google-constellation/oauth/readiness"

if ($health -ne 200 -or $login -ne 200 -or $session -ne 200) {
    throw "Public web transport did not expose only the expected unauthenticated entry points"
}
if ($bootstrap -ne 401 -or $opportunities -ne 401 -or $googleCaps -ne 401 -or $oauthReadiness -ne 401) {
    throw "Application auth boundary failed: a protected HealthIA endpoint did not return 401"
}

$callback = $serviceUrl.TrimEnd('/') + "/api/google-constellation/oauth/callback"
Write-Host "HEALTHIA_GOOGLE_LIVE_PREREQS_PASS"
Write-Host "Public HealthIA ONE URL: $serviceUrl"
Write-Host "Exact OAuth callback: $callback"
Write-Host "Places API key resource: $keyResource"
Write-Host "Places API key secret version: $mapsVersion"
Write-Host "Places API key value: not displayed"
Write-Host "Places secret accessor: serviceAccount:$runtimeEmail"
Write-Host "Protected anonymous probes: 401 PASS"
