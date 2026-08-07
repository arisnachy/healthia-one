param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$SecretName = "healthia-gemini-api-key",
    [string]$TopicName = "healthia-agentic-events",
    [string]$SubscriptionName = "healthia-agentic-events-push",
    [string]$SchedulerName = "healthia-agentic-tick",
    [switch]$DeleteSecret,
    [switch]$DeleteServiceAccounts,
    [switch]$DeleteProject
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud CLI no esta instalado o no esta en PATH." }

function Remove-GcloudResource {
    param([string[]]$Arguments, [string]$Label)
    & gcloud @Arguments *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Eliminado: $Label" -ForegroundColor Green
    } else {
        Write-Host "No se elimino $Label (puede que ya no exista)." -ForegroundColor DarkYellow
    }
}

Write-Host "HEALTHIA ONE · LIMPIEZA CLOUD" -ForegroundColor Yellow
Write-Host "Se eliminaran Cloud Run, Pub/Sub y Scheduler para detener gasto recurrente." -ForegroundColor Yellow
Write-Host "Firestore NO se elimina por defecto para evitar perdida accidental de evidencia." -ForegroundColor Cyan
if ($DeleteProject) { Write-Host "-DeleteProject programara la eliminacion COMPLETA del proyecto." -ForegroundColor Red }
$confirmation = Read-Host "Escribe DELETE para continuar"
if ($confirmation -ne "DELETE") { throw "Limpieza cancelada." }

Remove-GcloudResource @("scheduler", "jobs", "delete", $SchedulerName, "--location", $Region, "--project", $ProjectId, "--quiet") "Cloud Scheduler $SchedulerName"
Remove-GcloudResource @("pubsub", "subscriptions", "delete", $SubscriptionName, "--project", $ProjectId, "--quiet") "Pub/Sub subscription $SubscriptionName"
Remove-GcloudResource @("pubsub", "topics", "delete", $TopicName, "--project", $ProjectId, "--quiet") "Pub/Sub topic $TopicName"
Remove-GcloudResource @("run", "services", "delete", $ServiceName, "--project", $ProjectId, "--region", $Region, "--quiet") "Cloud Run $ServiceName"

if ($DeleteSecret) {
    Remove-GcloudResource @("secrets", "delete", $SecretName, "--project", $ProjectId, "--quiet") "Secret Manager $SecretName"
}
if ($DeleteServiceAccounts) {
    foreach ($account in @("healthia-runtime@$ProjectId.iam.gserviceaccount.com", "healthia-pubsub-push@$ProjectId.iam.gserviceaccount.com")) {
        Remove-GcloudResource @("iam", "service-accounts", "delete", $account, "--project", $ProjectId, "--quiet") "service account $account"
    }
}

if ($DeleteProject) {
    & gcloud projects delete $ProjectId --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "No se pudo programar la eliminacion del proyecto." }
    Write-Host "Proyecto programado para eliminacion." -ForegroundColor Green
} else {
    Write-Host "" 
    Write-Host "Recursos de ejecucion eliminados. Revisa Cloud Billing para confirmar consumo detenido." -ForegroundColor Green
    Write-Host "Firestore y Artifact Registry pueden conservar evidencia y almacenamiento; elimina el proyecto solo cuando ya no los necesites." -ForegroundColor Yellow
}
