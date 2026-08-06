param(
    [switch]$Gemini,
    [int]$Port = 8000,
    [string]$Model = "gemini-3.6-flash"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "No se encontró .venv. Ejecuta: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e `".[test]`""
}

$secureKey = $null
$bstr = [IntPtr]::Zero
$plainKey = $null

try {
    $env:HEALTHIA_ENV = "local"
    $env:HEALTHIA_STORE_BACKEND = "json"
    $env:HEALTHIA_DATA_PATH = ".healthia-one/state.json"
    $env:HEALTHIA_PROACTIVE_INTERVAL_SECONDS = "20"

    if ($Gemini) {
        $secureKey = Read-Host "Gemini API key (entrada protegida)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            throw "No se proporcionó una API key."
        }
        $env:HEALTHIA_LLM_BACKEND = "gemini_api"
        $env:HEALTHIA_MODEL = $Model
        $env:GOOGLE_API_KEY = $plainKey
        Write-Host "HealthIA ONE · Google ADK/Gemini configurado para el proceso actual" -ForegroundColor Cyan
    }
    else {
        $env:HEALTHIA_LLM_BACKEND = "mock"
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
        Write-Host "HealthIA ONE · modo determinista local, sin consumo de API" -ForegroundColor Cyan
    }

    Write-Host "Abre http://127.0.0.1:$Port" -ForegroundColor Green
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $plainKey = $null
    Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_LLM_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_MODEL -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_STORE_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_DATA_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:HEALTHIA_PROACTIVE_INTERVAL_SECONDS -ErrorAction SilentlyContinue
    Write-Host "Variables temporales eliminadas." -ForegroundColor DarkGray
}
