param(
    [Parameter(Mandatory = $true)] [string] $ProjectId,
    [Parameter(Mandatory = $true)] [string] $ClientSecretJsonPath,
    [Parameter(Mandatory = $true)] [string] $RedirectUri,
    [string] $SecretName = "healthia-google-oauth-client",
    [switch] $Confirmed
)

$ErrorActionPreference = "Stop"

function Require-Command([string] $Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Require-Command "gcloud"

if (-not (Test-Path -LiteralPath $ClientSecretJsonPath -PathType Leaf)) {
    throw "ClientSecretJsonPath does not exist or is not a file"
}

$redirect = $null
if (-not [uri]::TryCreate($RedirectUri, [System.UriKind]::Absolute, [ref] $redirect)) {
    throw "RedirectUri must be an absolute URI"
}
if ($redirect.Scheme -ne "https") {
    throw "RedirectUri must use HTTPS"
}
if ($redirect.AbsolutePath -ne "/api/google-constellation/oauth/callback") {
    throw "RedirectUri path must be /api/google-constellation/oauth/callback"
}

try {
    $document = Get-Content -LiteralPath $ClientSecretJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    throw "The downloaded Google OAuth client file is not valid JSON"
}

# Google currently downloads Web OAuth credentials as { "web": { ... } }.
# HealthIA deliberately accepts only the web application shape here. The client
# secret is never printed, placed in command-line arguments, or committed.
$web = $document.web
if ($null -eq $web) {
    throw "The Google OAuth credential file is not a Web application client (missing top-level 'web')"
}

$clientId = [string] $web.client_id
$clientSecret = [string] $web.client_secret
if ([string]::IsNullOrWhiteSpace($clientId) -or -not $clientId.EndsWith(".apps.googleusercontent.com")) {
    throw "The Google OAuth Web client_id is missing or invalid"
}
if ([string]::IsNullOrWhiteSpace($clientSecret) -or $clientSecret.Length -lt 8) {
    throw "The Google OAuth Web client_secret is missing or invalid"
}

$authorizedRedirects = @($web.redirect_uris | ForEach-Object { [string] $_ })
if ($authorizedRedirects -notcontains $RedirectUri) {
    throw "The downloaded Web Client does not contain the exact HealthIA RedirectUri. Fix Authorized redirect URIs in Google Auth Platform and download the client again."
}

if (-not $Confirmed) {
    Write-Host "HEALTHIA_GOOGLE_OAUTH_CLIENT_IMPORT_NOT_CONFIRMED"
    Write-Host "Validated: Web application client + exact HTTPS callback."
    Write-Host "No Secret Manager mutation was performed."
    exit 0
}

$enabled = @(gcloud services list --project $ProjectId --enabled --format="value(config.name)")
if ($enabled -notcontains "secretmanager.googleapis.com") {
    throw "Secret Manager API is not enabled. This script will not enable APIs silently."
}

$existing = gcloud secrets describe $SecretName --project $ProjectId --format="value(name)" 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($existing)) {
    & gcloud secrets create $SecretName --project $ProjectId --replication-policy automatic --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the OAuth client Secret Manager container"
    }
}

# Store only what HealthIA's runtime needs. The downloaded file itself remains
# outside the repository and is never uploaded. Piping through stdin keeps the
# client secret out of process arguments and shell history.
$compact = [ordered]@{
    client_id = $clientId
    client_secret = $clientSecret
} | ConvertTo-Json -Compress

try {
    $version = $compact | & gcloud secrets versions add $SecretName `
        --project $ProjectId `
        --data-file=- `
        --format="value(name)" `
        --quiet
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string] $version)) {
        throw "Secret Manager did not return a new OAuth client version"
    }
} finally {
    $compact = $null
    $clientSecret = $null
    $document = $null
    $web = $null
}

Write-Host "HEALTHIA_GOOGLE_OAUTH_CLIENT_IMPORTED"
Write-Host "OAuth client secret version: $version"
Write-Host "Redirect URI validated: $RedirectUri"
Write-Host "OAuth client payload: not displayed"
Write-Host "Downloaded client_secret.json: not copied into the repository"
