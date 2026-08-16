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

function Add-SecretVersionFromMemory([string] $Name, [string] $Payload) {
    $Payload = $Payload.TrimStart([char] 0xFEFF)
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    if ($GcloudSdkRoot) {
        $startInfo.FileName = Join-Path $GcloudSdkRoot "platform\bundledpython\python.exe"
        $gcloudEntrypoint = Join-Path $GcloudSdkRoot "lib\gcloud.py"
        $startInfo.Arguments = "-S `"$gcloudEntrypoint`" secrets versions add $Name --project $ProjectId --data-file=- --format=`"value(name)`" --quiet"
    } else {
        $startInfo.FileName = $GcloudCommand
        $startInfo.Arguments = "secrets versions add $Name --project $ProjectId --data-file=- --format=`"value(name)`" --quiet"
    }
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    try {
        # Write the key directly from memory. Windows PowerShell native
        # pipelines can prepend a BOM, which makes the API-key HTTP header
        # invalid at runtime.
        $process.StandardInput.Write($Payload)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "Secret Manager rejected the Places key without exposing it"
        }
        return $stdout.Trim()
    } finally {
        $process.Dispose()
        $stderr = $null
        $stdout = $null
    }
}

Require-Command "gcloud"
$gcloudCmd = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue
$GcloudCommand = if ($gcloudCmd) { $gcloudCmd.Source } else { (Get-Command "gcloud").Source }
$GcloudSdkRoot = if ($gcloudCmd) { Split-Path (Split-Path $gcloudCmd.Source -Parent) -Parent } else { $null }

if ($WebServiceName -ne "healthia-one-web-demo") {
    throw "WebServiceName must be the isolated healthia-one-web-demo service; refusing to expose any other Cloud Run service"
}

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

$enabled = @(gcloud services list --project $ProjectId --enabled --format="value(config.name)")
foreach ($api in @("run.googleapis.com", "secretmanager.googleapis.com")) {
    if ($enabled -notcontains $api) {
        throw "Required existing API is not enabled: $api. No live promotion was attempted."
    }
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

$keyMetadata = & gcloud services api-keys describe $keyResource --project $ProjectId --format=json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $null -eq $keyMetadata) {
    throw "Unable to verify the Places API key restrictions"
}
$apiTargets = @($keyMetadata.restrictions.apiTargets)
if ($apiTargets.Count -ne 1 -or [string] $apiTargets[0].service -ne "places.googleapis.com") {
    throw "Refusing to reuse an API key that is not restricted exclusively to places.googleapis.com"
}

$mapsKey = (& gcloud services api-keys get-key-string $keyResource --project $ProjectId --format="value(keyString)").Trim().TrimStart([char] 0xFEFF)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mapsKey)) {
    throw "Unable to retrieve the Places API key string"
}

$secretExists = & gcloud secrets describe $MapsSecretName --project $ProjectId --format="value(name)" 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string] $secretExists)) {
    Invoke-Gcloud @("secrets", "create", $MapsSecretName, "--project", $ProjectId, "--replication-policy", "automatic", "--quiet")
}

try {
    $mapsVersion = Add-SecretVersionFromMemory $MapsSecretName $mapsKey
    if ([string]::IsNullOrWhiteSpace([string] $mapsVersion)) {
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
    $request = [System.Net.HttpWebRequest]::Create($serviceUrl.TrimEnd('/') + $Path)
    $request.Method = "GET"
    $request.AllowAutoRedirect = $false
    $request.Timeout = 15000
    try {
        $response = $request.GetResponse()
        try {
            return [int] ([System.Net.HttpWebResponse] $response).StatusCode
        } finally {
            $response.Dispose()
        }
    } catch {
        $webException = $_.Exception
        while ($webException -and -not ($webException -is [System.Net.WebException])) {
            $webException = $webException.InnerException
        }
        if ($webException -and $webException.Response) {
            $errorResponse = [System.Net.HttpWebResponse] $webException.Response
            try {
                return [int] $errorResponse.StatusCode
            } finally {
                $errorResponse.Dispose()
            }
        }
        return 0
    }
}

$readiness = Probe "/api/readiness"
$healthz = Probe "/healthz"
$login = Probe "/login"
$session = Probe "/api/auth/session"
$bootstrap = Probe "/api/bootstrap"
$opportunities = Probe "/api/opportunities"
$googleCaps = Probe "/api/google-constellation/capabilities"
$oauthReadiness = Probe "/api/google-constellation/oauth/readiness"

if ($readiness -ne 200 -or $login -ne 200 -or $session -ne 200) {
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
Write-Host "Cloud Run readiness probe: /api/readiness 200 PASS"
Write-Host "Cloud Run reserved /healthz observation: HTTP $healthz (not used as the deployed readiness gate)"
Write-Host "Protected anonymous probes: 401 PASS"
