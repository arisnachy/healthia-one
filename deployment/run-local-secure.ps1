param(
    [switch]$Gemini,
    [switch]$Mock,
    [switch]$SkipApiCheck,
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

if ($Gemini -and $Mock) {
    throw "Usa -Gemini o -Mock, no ambos. Gemini es el modo predeterminado."
}
if (-not (Test-Path $venvPython)) {
    throw 'No se encontro .venv. Ejecuta: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[test]"'
}
if (-not (Test-Path $probeScript)) {
    throw "No se encontro deployment/verify_google_ai.py. Actualiza el repositorio antes de iniciar."
}

$useGemini = -not $Mock
$secureKey = $null
$bstr = [IntPtr]::Zero
$plainKey = $null
$previousLocation = Get-Location

try {
    Set-Location $projectRoot
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:HEALTHIA_ENV = "local"
    $env:HEALTHIA_STORE_BACKEND = "json"
    $env:HEALTHIA_DATA_PATH = ".healthia-one/state.json"
    $env:HEALTHIA_PROACTIVE_INTERVAL_SECONDS = "20"

    if ($useGemini) {
        $plainKey = $env:GEMINI_API_KEY
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            $secureKey = Read-Host "Gemini API key (entrada protegida)" -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
            $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            throw "No se proporciono una API key. Usa -Mock para iniciar sin Google AI."
        }

        $env:HEALTHIA_LLM_BACKEND = "gemini_api"
        $env:HEALTHIA_MODEL = $Model
        $env:GEMINI_API_KEY = $plainKey
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue

        if (-not $SkipApiCheck) {
            Write-Host "Verificando SDK, clave, cuota, modelo e Interactions API..." -ForegroundColor DarkCyan
            $probeOutput = & $venvPython $probeScript 2>&1
            $probeExitCode = $LASTEXITCODE
            $probeOutput | ForEach-Object { Write-Host $_ }
            if ($probeExitCode -ne 0) {
                throw 'Google AI no supero la verificacion real. El mensaje HEALTHIA_GOOGLE_AI_ERROR indica si fallo autenticacion, cuota, modelo, SDK o red. Actualiza con: .\.venv\Scripts\python.exe -m pip install -e ".[test]"'
            }
        }
        Write-Host "HealthIA ONE - Gemini activo en el chat principal - store=false" -ForegroundColor Cyan
    }
    else {
        $env:HEALTHIA_LLM_BACKEND = "mock"
        Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
        Write-Host "HealthIA ONE - modo determinista local, sin consumo de API" -ForegroundColor Cyan
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
    Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    Set-Location $previousLocation
    Write-Host "Variables temporales eliminadas." -ForegroundColor DarkGray
}
