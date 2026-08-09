param(
    [switch]$GuardedAi,
    [switch]$Gemini,
    [switch]$Mock,
    [switch]$StartEnabled,
    [switch]$LiveProbe,
    [switch]$Reload,
    [switch]$AllowLan,
    [switch]$SkipApiCheck,
    [ValidateRange(1, 100)][int]$RequestLimit = 12,
    [ValidateRange(256, 4096)][int]$MaxOutputTokens = 1400,
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

function Ensure-LocalSecret([string]$Path) {
    if (-not (Test-Path $Path)) {
        $parent = Split-Path -Parent $Path
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        $bytes = New-Object byte[] 48
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret = [Convert]::ToBase64String($bytes)
        [System.IO.File]::WriteAllText($Path, $secret, $utf8)
    }
    return [System.IO.File]::ReadAllText($Path, $utf8).Trim()
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
    $env:HEALTHIA_ACCOUNTS_PATH = ".healthia-one/accounts.json"
    $env:HEALTHIA_AUTH_REQUIRED = "true"
    $env:HEALTHIA_ALLOW_REGISTRATION = "true"
    $env:HEALTHIA_SESSION_SECRET = Ensure-LocalSecret (Join-Path $projectRoot ".healthia-one\session-secret")
    $env:HEALTHIA_DEVICE_TOKEN_SECRET = Ensure-LocalSecret (Join-Path $projectRoot ".healthia-one\device-token-secret")
    $env:HEALTHIA_PROACTIVE_INTERVAL_SECONDS = "20"
    $env:HEALTHIA_PROACTIVE_ENABLED = "false"
    $env:HEALTHIA_COST_CONTROL_UI = "true"

    if ($useGuardedAi) {
        $plainKey = $env:GEMINI_API_KEY
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            $secureKey = Read-Host "Gemini API key (entrada protegida; no se guarda en el repo)" -AsSecureString
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
        Write-Host "HealthIA ONE - Google AI configurado y protegido" -ForegroundColor Cyan
        Write-Host "Limite duro restante: $remainingLimit solicitudes; salida maxima: $MaxOutputTokens tokens." -ForegroundColor Cyan
        Write-Host "Preguntas clinicas: Gemini + Google ADK; no se mostraran bloques precargados si la IA falla." -ForegroundColor Cyan
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
        Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
        Write-Host "HealthIA ONE - LOCAL SEGURO - cero llamadas a Google AI" -ForegroundColor Green
        Write-Host "Los bloques clinicos no fingiran ser IA: si Gemini no esta activo, se mostrara el estado no disponible." -ForegroundColor DarkGreen
    }

    Write-Host "Cuenta del paciente: login/logout ACTIVOS; crea tu cuenta en la primera apertura." -ForegroundColor Green
    Write-Host "Navegador en esta PC: http://127.0.0.1:$Port" -ForegroundColor Green
    if ($AllowLan) {
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
    }

    $bindHost = if ($AllowLan) { "0.0.0.0" } else { "127.0.0.1" }
    $uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $bindHost, "--port", [string]$Port)
    if ($Reload) { $uvicornArgs += "--reload" }
    & $venvPython @uvicornArgs
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
    Remove-Item Env:HEALTHIA_ACCOUNTS_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_AUTH_REQUIRED -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_ALLOW_REGISTRATION -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_SESSION_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_DEVICE_TOKEN_SECRET -ErrorAction SilentlyContinue
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
