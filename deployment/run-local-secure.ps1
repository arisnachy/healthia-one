param(
    [switch]$Gemini,
    [switch]$Mock,
    [switch]$SkipApiCheck,
    [int]$Port = 8000,
    [string]$Model = "gemini-3.6-flash"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if ($Gemini -and $Mock) {
    throw "Usa -Gemini o -Mock, no ambos. Gemini es el modo predeterminado."
}
if (-not (Test-Path $venvPython)) {
    throw "No se encontró .venv. Ejecuta: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e `\".[test]`\""
}

$useGemini = -not $Mock
$secureKey = $null
$bstr = [IntPtr]::Zero
$plainKey = $null

try {
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
            throw "No se proporcionó una API key. Usa -Mock para iniciar sin Google AI."
        }
        $env:HEALTHIA_LLM_BACKEND = "gemini_api"
        $env:HEALTHIA_MODEL = $Model
        $env:GEMINI_API_KEY = $plainKey
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue

        if (-not $SkipApiCheck) {
            Write-Host "Verificando la clave y el modelo $Model…" -ForegroundColor DarkCyan
            $probe = @'
from google import genai
import os
client = genai.Client()
model = client.models.get(model=os.environ["HEALTHIA_MODEL"])
print(f"Google AI listo: {getattr(model, 'name', os.environ['HEALTHIA_MODEL'])}")
'@
            & $venvPython -c $probe
            if ($LASTEXITCODE -ne 0) { throw "Google AI no superó la verificación previa." }
        }
        Write-Host "HealthIA ONE · Gemini activo en el chat principal" -ForegroundColor Cyan
    }
    else {
        $env:HEALTHIA_LLM_BACKEND = "mock"
        Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
        Write-Host "HealthIA ONE · modo determinista local, sin consumo de API" -ForegroundColor Cyan
    }

    Write-Host "Abre http://127.0.0.1:$Port" -ForegroundColor Green
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
    Write-Host "Variables temporales eliminadas." -ForegroundColor DarkGray
}
