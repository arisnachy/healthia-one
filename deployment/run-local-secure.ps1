param(
    [switch]$GuardedAi,
    [switch]$Gemini,
    [switch]$Mock,
    [switch]$StartEnabled,
    [switch]$LiveProbe,
    [switch]$SkipApiCheck,
    [ValidateRange(1, 100)][int]$RequestLimit = 10,
    [ValidateRange(64, 4096)][int]$MaxOutputTokens = 700,
    [int]$Port = 8000,
    [string]$Model = "gemini-3.6-flash"
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$probeScript = Join-Path $PSScriptRoot "verify_google_ai.py"

$useGuardedAi = $GuardedAi -or $Gemini
if ($Mock -and $useGuardedAi) {
    throw "Usa modo local o -GuardedAi, no ambos."
}
if ($Gemini) {
    Write-Host "-Gemini se mantiene como alias. Usa -GuardedAi para dejar claro que existe un limite de gasto." -ForegroundColor Yellow
}
if ($SkipApiCheck) {
    Write-Host "-SkipApiCheck ya no es necesario: el arranque no consume API salvo que indiques -LiveProbe." -ForegroundColor DarkYellow
}
if (-not (Test-Path $venvPython)) {
    throw 'No se encontro .venv. Ejecuta: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[test]"'
}
if ($LiveProbe -and -not (Test-Path $probeScript)) {
    throw "No se encontro deployment/verify_google_ai.py. Actualiza el repositorio antes de iniciar."
}
if ($LiveProbe -and -not $useGuardedAi) {
    throw "-LiveProbe requiere -GuardedAi porque realiza una llamada real y potencialmente facturable."
}

$secureKey = $null
$bstr = [IntPtr]::Zero
$plainKey = $null
$previousLocation = Get-Location
$remainingLimit = if ($useGuardedAi) { $RequestLimit } else { 0 }

try {
    Set-Location $projectRoot
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:HEALTHIA_ENV = "local"
    $env:HEALTHIA_STORE_BACKEND = "json"
    $env:HEALTHIA_DATA_PATH = ".healthia-one/state.json"
    $env:HEALTHIA_PROACTIVE_INTERVAL_SECONDS = "20"
    $env:HEALTHIA_COST_CONTROL_UI = "true"

    if ($useGuardedAi) {
        $plainKey = $env:GEMINI_API_KEY
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            $secureKey = Read-Host "Gemini API key (entrada protegida)" -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
            $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            throw "No se proporciono una API key. Inicia sin -GuardedAi para probar sin consumo."
        }

        $env:HEALTHIA_LLM_BACKEND = "gemini_api"
        $env:HEALTHIA_MODEL = $Model
        $env:GEMINI_API_KEY = $plainKey
        $env:HEALTHIA_COST_MODE = "guarded"
        $env:HEALTHIA_AI_MAX_OUTPUT_TOKENS = "$MaxOutputTokens"
        $env:HEALTHIA_PROACTIVE_ENABLED = "false"
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue

        if ($LiveProbe) {
            Write-Host "Ejecutando una unica prueba real de Google AI..." -ForegroundColor DarkCyan
            $probeOutput = & $venvPython $probeScript 2>&1
            $probeExitCode = $LASTEXITCODE
            $probeOutput | ForEach-Object { Write-Host $_ }
            if ($probeExitCode -ne 0) {
                throw 'Google AI no supero la prueba real. El mensaje HEALTHIA_GOOGLE_AI_ERROR indica autenticacion, cuota, modelo, SDK o red.'
            }
            $remainingLimit = [Math]::Max(0, $remainingLimit - 1)
            Write-Host "La prueba consumio 1 de las $RequestLimit solicitudes permitidas para esta ejecucion." -ForegroundColor Yellow
        }

        $env:HEALTHIA_AI_REQUEST_LIMIT = "$remainingLimit"
        $env:HEALTHIA_COST_GUARD_START_ENABLED = if ($StartEnabled -and $remainingLimit -gt 0) { "true" } else { "false" }
        Write-Host "HealthIA ONE - Google AI configurado pero protegido" -ForegroundColor Cyan
        Write-Host "Limite duro restante: $remainingLimit solicitudes; salida maxima: $MaxOutputTokens tokens." -ForegroundColor Cyan
        if (-not $StartEnabled) {
            Write-Host "El interruptor inicia APAGADO. Activalo desde Control de costos cuando quieras probar." -ForegroundColor Green
        }
    }
    else {
        $env:HEALTHIA_LLM_BACKEND = "mock"
        $env:HEALTHIA_COST_MODE = "local"
        $env:HEALTHIA_AI_REQUEST_LIMIT = "0"
        $env:HEALTHIA_COST_GUARD_START_ENABLED = "false"
        $env:HEALTHIA_AI_MAX_OUTPUT_TOKENS = "$MaxOutputTokens"
        $env:HEALTHIA_PROACTIVE_ENABLED = "true"
        Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
        Write-Host "HealthIA ONE - LOCAL SEGURO - cero llamadas a Google AI" -ForegroundColor Green
    }

    Write-Host "Navegador en esta PC: http://127.0.0.1:$Port" -ForegroundColor Green
    try {
        $lanAddresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.AddressState -eq "Preferred"
            } |
            Select-Object -ExpandProperty IPAddress -Unique
        foreach ($address in $lanAddresses) {
            Write-Host "Telefono en la misma Wi-Fi: http://${address}:$Port" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "No pude detectar la IP LAN automaticamente; usa ipconfig para verla." -ForegroundColor Yellow
    }

    & $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port $Port --reload
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $plainKey = $null
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_LLM_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_MODEL -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_STORE_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_DATA_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_PROACTIVE_INTERVAL_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_PROACTIVE_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_COST_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_AI_REQUEST_LIMIT -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_COST_GUARD_START_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_COST_CONTROL_UI -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_AI_MAX_OUTPUT_TOKENS -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    Set-Location $previousLocation
    Write-Host "Variables temporales eliminadas." -ForegroundColor DarkGray
}
