param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$RuntimeServiceAccount = "healthia-one-demo",
    [string]$ServiceName = "healthia-one-demo",
    [string]$TemplateId = "healthia-one-safety",
    [ValidateSet("high", "medium-and-above")][string]$PromptInjectionConfidence = "high",
    [switch]$Confirmed
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is required."
}

$runtimeEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"

if (-not $Confirmed) {
    $answer = Read-Host "Type ONE-SAFETY to configure Model Armor + Cloud Trace"
    if ($answer -ne "ONE-SAFETY") { throw "Configuration cancelled." }
}

& gcloud config set project $ProjectId | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not select Google Cloud project." }

# These APIs must already be enabled by the project owner/provisioning identity.
Write-Host "Required pre-enabled APIs: modelarmor.googleapis.com, cloudtrace.googleapis.com" -ForegroundColor Cyan

function Grant-Role([string]$Role) {
    & gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$runtimeEmail" `
        --role $Role `
        --condition=None `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not grant $Role to $runtimeEmail." }
}

Grant-Role "roles/modelarmor.user"
Grant-Role "roles/modelarmor.viewer"
Grant-Role "roles/cloudtrace.agent"

& gcloud model-armor templates describe $TemplateId --location $Region --project $ProjectId --format "value(name)" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    & gcloud model-armor templates create $TemplateId `
        --location $Region `
        --project $ProjectId `
        --pi-and-jailbreak-filter-settings-enforcement=enabled `
        --pi-and-jailbreak-filter-settings-confidence-level=$PromptInjectionConfidence `
        --malicious-uri-filter-settings-enforcement=enabled `
        --template-metadata-log-sanitize-operations `
        --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Model Armor template creation failed." }
}

& gcloud run services update $ServiceName `
    --project $ProjectId `
    --region $Region `
    --update-env-vars "HEALTHIA_MODEL_ARMOR_ENABLED=true,HEALTHIA_MODEL_ARMOR_FAIL_CLOSED=true,HEALTHIA_MODEL_ARMOR_LOCATION=$Region,HEALTHIA_MODEL_ARMOR_TEMPLATE_ID=$TemplateId,HEALTHIA_OTEL_ENABLED=true,HEALTHIA_CLOUD_TRACE_ENABLED=true,HEALTHIA_OTEL_SERVICE_NAME=healthia-one" `
    --quiet | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Cloud Run ONE SAFETY configuration failed." }

Write-Host "ONE SAFETY cloud configuration applied." -ForegroundColor Green
Write-Host "Verify the authenticated proof surface at /security and /api/operations/security." -ForegroundColor Cyan
