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
    throw 'No se encontró .venv. Ejecuta: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[test]"'
}

$useGemini = -not $Mock
$secureKey = $null
$bstr = [IntPtr]::Zero
$plainKey = $null
$previousLocation = Get-Location

try {
    Set-Location $projectRoot
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
            Write-Host "Verificando SDK, clave, modelo e Interactions API…" -ForegroundColor DarkCyan
            $probe = @'
from importlib.metadata import version
from google import genai
import os

sdk_version = version("google-genai")
major = int(sdk_version.split(".", 1)[0])
if major < 2:
    raise RuntimeError(f"google-genai {sdk_version} es incompatible; instala la rama 2.x")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
model_name = os.environ["HEALTHIA_MODEL"]
model = client.models.get(model=model_name)
interaction = client.interactions.create(
    model=model_name,
    input="Responde exactamente con la palabra OK.",
)
text = str(getattr(interaction, "output_text", "") or "").strip()
if not text:
    outputs = getattr(interaction, "outputs", None) or []
    text = next((str(getattr(item, "text", "") or "").strip() for item in reversed(outputs) if str(getattr(item, "text", "") or "").strip()), "")
if not text:
    raise RuntimeError("Gemini respondió sin texto utilizable")
print(f"Google AI listo: {getattr(model, 'name', model_name)} · google-genai {sdk_version} · respuesta {text[:24]}")
'@
            & $venvPython -c $probe
            if ($LASTEXITCODE -ne 0) {
                throw 'Google AI no superó la verificación. Actualiza dependencias con: .\.venv\Scripts\python.exe -m pip install -e ".[test]"'
            }
        }
        Write-Host "HealthIA ONE · Gemini activo en el chat principal" -ForegroundColor Cyan
    }
    else {
        $env:HEALTHIA_LLM_BACKEND = "mock"
        Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
        Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
        Write-Host "HealthIA ONE · modo determinista local, sin consumo de API" -ForegroundColor Cyan
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
            Write-Host "Teléfono en la misma Wi-Fi: http://${address}:$Port" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "No pude detectar la IP LAN automáticamente; usa ipconfig para verla." -ForegroundColor Yellow
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
    Set-Location $previousLocation
    Write-Host "Variables temporales eliminadas." -ForegroundColor DarkGray
}
