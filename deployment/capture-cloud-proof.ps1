param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$ServiceName = "healthia-one-demo",
    [string]$SchedulerName = "healthia-agentic-tick",
    [string]$OutputDirectory = "dist/cloud-proof",
    [ValidateRange(30, 300)][int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud CLI no esta instalado o no esta en PATH." }

function Get-IdentityToken {
    $token = (& gcloud auth print-identity-token).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $token) { throw "No se pudo obtener un identity token para Cloud Run." }
    return $token
}

function Invoke-HealthIA {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST")][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body = $null
    )
    $headers = @{ Authorization = "Bearer $(Get-IdentityToken)" }
    $uri = "$script:ServiceUrl$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 60
    }
    $json = $Body | ConvertTo-Json -Depth 12 -Compress
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body $json -TimeoutSec 60
}

function Get-MissionRuns {
    return Invoke-HealthIA -Method GET -Path "/api/judge/mission-runs?limit=20"
}

function Wait-ForNewRun {
    param([int]$PreviousCount, [string]$Label)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $payload = Get-MissionRuns
        if ([int]$payload.count -gt $PreviousCount) {
            $run = $payload.runs | Select-Object -First 1
            if (-not $run) { continue }
            if ($run.runtime -ne "google_adk") {
                throw "$Label no uso Google ADK. Runtime observado: $($run.runtime). Error: $($run.error)"
            }
            if ($run.status -ne "completed") { throw "$Label no termino correctamente: $($run.status)" }
            return $run
        }
    }
    throw "Timeout esperando $Label."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$script:ServiceUrl = (& gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $script:ServiceUrl) { throw "No se encontro el servicio Cloud Run $ServiceName." }

Write-Host "HEALTHIA ONE · PRUEBA CLOUD REAL" -ForegroundColor Cyan
Write-Host "Servicio: $script:ServiceUrl" -ForegroundColor White
Write-Host "Condicion: Google ADK + Pub/Sub + Firestore + cierre verificable, con maximo 6 llamadas reservadas." -ForegroundColor Green

$readinessBefore = Invoke-HealthIA -Method GET -Path "/api/readiness"
if ($readinessBefore.store_backend -ne "firestore") { throw "El runtime no esta usando Firestore." }
if ($readinessBefore.mission_runtime -ne "adk") { throw "El runtime de misiones no esta configurado como ADK." }
if ($readinessBefore.event_dispatch_backend -ne "pubsub") { throw "El dispatch durable no esta usando Pub/Sub." }
if (-not $readinessBefore.adk_ready) { throw "ADK/Gemini no esta listo en Cloud Run." }
if ([int]$readinessBefore.cost_control.requests_remaining -lt 6) {
    throw "Quedan menos de 6 llamadas reservables en esta instancia. Redespliega el servicio antes de capturar la prueba."
}

$reset = Invoke-HealthIA -Method POST -Path "/api/demo/reset"
if (-not $reset.reset) { throw "No se pudo reiniciar el paciente sintetico." }
$initialRuns = Get-MissionRuns
$initialCount = [int]$initialRuns.count

# 1) Autonomous background task: Scheduler -> Pub/Sub -> ADK -> consultation packet -> completed mission.
& gcloud scheduler jobs run $SchedulerName --location $Region --project $ProjectId --quiet | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Cloud Scheduler no pudo publicar el evento de prueba." }
$schedulerRun = Wait-ForNewRun -PreviousCount $initialCount -Label "mision del scheduler"
if (-not $schedulerRun.mission_id -or $schedulerRun.artifact_ids.Count -lt 1) {
    throw "La mision autonoma del scheduler no creo mision y artefacto verificable."
}
$schedulerTrace = Invoke-HealthIA -Method GET -Path "/api/judge/trace/$($schedulerRun.correlation_id)"
if ($schedulerTrace.mission.status -ne "completed") { throw "La tarea del scheduler no cerro su mision." }

# 2) Event-driven mission starts from a synthetic but real Cloud request and is delivered through Pub/Sub.
$beforeFirstVital = [int](Get-MissionRuns).count
$firstVital = Invoke-HealthIA -Method POST -Path "/api/vitals" -Body @{
    systolic = 165
    diastolic = 102
    pulse = 78
    source = @{ source_type = "synthetic_cloud_proof"; source_id = "judge-high-bp"; verified = $true }
}
$firstRun = Wait-ForNewRun -PreviousCount $beforeFirstVital -Label "apertura de seguimiento"
$firstTrace = Invoke-HealthIA -Method GET -Path "/api/judge/trace/$($firstRun.correlation_id)"
if ($firstTrace.mission.status -ne "waiting_patient") { throw "La primera evidencia no abrio el seguimiento esperado." }

# 3) A second event satisfies the closure condition and ADK closes the mission with an artifact.
$beforeSecondVital = [int](Get-MissionRuns).count
$secondVital = Invoke-HealthIA -Method POST -Path "/api/vitals" -Body @{
    systolic = 138
    diastolic = 88
    pulse = 74
    source = @{ source_type = "synthetic_cloud_proof"; source_id = "judge-repeat-bp"; verified = $true }
}
$secondRun = Wait-ForNewRun -PreviousCount $beforeSecondVital -Label "cierre de seguimiento"
$finalTrace = Invoke-HealthIA -Method GET -Path "/api/judge/trace/$($secondRun.correlation_id)"
if ($finalTrace.mission.status -ne "completed") { throw "La segunda evidencia no cerro la mision." }
if ($finalTrace.artifacts.Count -lt 1) { throw "El cierre no creo un artefacto verificable." }
$stages = @($finalTrace.run.events | ForEach-Object { $_.stage })
foreach ($required in @("trigger", "decision", "tool", "persistence", "closure")) {
    if ($stages -notcontains $required) { throw "La traza final no contiene la etapa $required." }
}

$readinessAfter = Invoke-HealthIA -Method GET -Path "/api/readiness"
if ([int]$readinessAfter.cost_control.requests_used -gt 6) { throw "El proof excedio el techo de seis llamadas reservadas." }

# Resource and log evidence. No credentials or secret payloads are included.
$serviceJson = & gcloud run services describe $ServiceName --project $ProjectId --region $Region --format json
$firestoreJson = & gcloud firestore databases describe --database="(default)" --project $ProjectId --format json
$schedulerJson = & gcloud scheduler jobs describe $SchedulerName --location $Region --project $ProjectId --format json
$logsJson = & gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$ServiceName AND textPayload:\"healthia_agentic_mission_completed\"" --project $ProjectId --limit 20 --freshness 30m --format json

$proof = [ordered]@{
    schema_version = 1
    captured_at_utc = [DateTime]::UtcNow.ToString("o")
    project_id = $ProjectId
    region = $Region
    service_name = $ServiceName
    service_url = $script:ServiceUrl
    source = "REAL_GOOGLE_CLOUD_PROOF"
    truth_boundary = "Synthetic medical inputs executed through the real Cloud Run, Pub/Sub, Firestore, Google ADK and Gemini runtime. No diagnosis or treatment change is performed."
    readiness_before = $readinessBefore
    scheduler_mission = $schedulerTrace
    first_vital = $firstVital
    first_mission = $firstTrace
    second_vital = $secondVital
    closed_mission = $finalTrace
    readiness_after = $readinessAfter
    checks = [ordered]@{
        firestore = $true
        pubsub = $true
        google_adk_three_runs = $true
        scheduler_background_action = $true
        closed_loop_mission = $true
        persistent_artifact = $true
        trace_stages = @("trigger", "decision", "tool", "persistence", "closure")
        max_reserved_model_calls = 6
        observed_reserved_calls = [int]$readinessAfter.cost_control.requests_used - [int]$readinessBefore.cost_control.requests_used
    }
}

$proofPath = Join-Path $OutputDirectory "healthia-cloud-proof.json"
$proof | ConvertTo-Json -Depth 30 | Set-Content -Path $proofPath -Encoding utf8
$serviceJson | Set-Content -Path (Join-Path $OutputDirectory "cloud-run-service.json") -Encoding utf8
$firestoreJson | Set-Content -Path (Join-Path $OutputDirectory "firestore-database.json") -Encoding utf8
$schedulerJson | Set-Content -Path (Join-Path $OutputDirectory "cloud-scheduler-job.json") -Encoding utf8
$logsJson | Set-Content -Path (Join-Path $OutputDirectory "cloud-run-agentic-logs.json") -Encoding utf8

Write-Host ""
Write-Host "CLOUD PROOF: PASS" -ForegroundColor Green
Write-Host "ADK runtimes: 3" -ForegroundColor Green
Write-Host "Mision de scheduler: COMPLETED" -ForegroundColor Green
Write-Host "Seguimiento por eventos: OPEN -> COMPLETED" -ForegroundColor Green
Write-Host "Artefacto persistido: SI" -ForegroundColor Green
Write-Host "Presupuesto reservado observado: $($proof.checks.observed_reserved_calls) / 6" -ForegroundColor Green
Write-Host "Evidencia: $proofPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ahora pausa todo gasto eliminando los recursos de ejecucion con remove-cloud-demo.ps1 cuando termines de grabar la consola." -ForegroundColor Yellow
