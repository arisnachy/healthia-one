from __future__ import annotations

from typing import Any


PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "id": "android_health_connect",
        "name": "Android Health Connect",
        "platform": "Android 9+",
        "status": "implemented",
        "connection_mode": "native_permission_and_pairing_code",
        "account_login": "not_shared_with_healthia",
        "requires_native_app": True,
        "summary": (
            "HealthIA Bridge solicita en el teléfono permisos de Health Connect por tipo de dato y envía "
            "únicamente los registros autorizados al backend de HealthIA vinculado."
        ),
        "patient_step": (
            "Instala HealthIA Bridge, escribe la dirección del backend y el código de seis dígitos, "
            "y luego concede los permisos de Health Connect."
        ),
    },
    {
        "id": "samsung_health_via_health_connect",
        "name": "Samsung Health / Galaxy Watch",
        "platform": "Samsung y Android",
        "status": "implemented_via_health_connect",
        "connection_mode": "samsung_health_to_health_connect_to_healthia",
        "account_login": "samsung_credentials_remain_inside_samsung_health",
        "requires_native_app": True,
        "summary": (
            "Samsung Health puede escribir en Health Connect los datos consentidos del teléfono y dispositivos "
            "Galaxy. El puente Android existente de HealthIA lee esos registros autorizados desde Health Connect."
        ),
        "patient_step": (
            "Activa la sincronización de Samsung Health con Health Connect y después concede acceso a "
            "HealthIA Bridge dentro de Health Connect."
        ),
    },
    {
        "id": "samsung_health_data_sdk",
        "name": "Samsung Health Data SDK (directo)",
        "platform": "Android 10+",
        "status": "planned_optional_adapter",
        "connection_mode": "native_samsung_permission",
        "account_login": "not_shared_with_healthia",
        "requires_native_app": True,
        "summary": (
            "Adaptador directo opcional para datos específicos de Samsung que no estén disponibles mediante "
            "Health Connect. La distribución pública requiere registro como socio de Samsung y firma de paquete aprobada."
        ),
        "patient_step": (
            "Cuando este adaptador esté disponible, concede en la aplicación Android únicamente los permisos "
            "seleccionados de Samsung Health."
        ),
    },
    {
        "id": "apple_healthkit",
        "name": "Apple Health / Apple Watch",
        "platform": "iPhone y Apple Watch",
        "status": "planned_native_ios_bridge",
        "connection_mode": "native_healthkit_permission",
        "account_login": "apple_id_not_shared_with_healthia",
        "requires_native_app": True,
        "summary": (
            "Un puente nativo de HealthIA para iOS debe solicitar autorización granular de HealthKit y cargar "
            "solo las muestras permitidas por la persona. El navegador web no puede leer HealthKit directamente."
        ),
        "patient_step": (
            "Instala el futuro puente HealthIA para iOS y aprueba en el iPhone los permisos de salud solicitados."
        ),
    },
    {
        "id": "fitbit",
        "name": "Fitbit",
        "platform": "Cuenta en la nube",
        "status": "planned_oauth_adapter",
        "connection_mode": "oauth2",
        "account_login": "provider_login_via_oauth",
        "requires_native_app": False,
        "summary": (
            "El paciente autoriza a HealthIA desde la pantalla OAuth de Fitbit; HealthIA nunca recibe la contraseña."
        ),
        "patient_step": (
            "Selecciona Conectar Fitbit y aprueba los permisos solicitados en la página de autorización de Fitbit."
        ),
    },
    {
        "id": "garmin",
        "name": "Garmin",
        "platform": "Cuenta en la nube",
        "status": "planned_partner_oauth_adapter",
        "connection_mode": "partner_api_oauth",
        "account_login": "provider_login_via_oauth",
        "requires_native_app": False,
        "summary": (
            "Un adaptador de producción requiere acceso al programa del proveedor y autorización consentida de su API."
        ),
        "patient_step": (
            "Autoriza la conexión de Garmin cuando HealthIA disponga de la aprobación de la API de producción."
        ),
    },
    {
        "id": "withings",
        "name": "Withings",
        "platform": "Cuenta en la nube",
        "status": "planned_oauth_adapter",
        "connection_mode": "oauth2",
        "account_login": "provider_login_via_oauth",
        "requires_native_app": False,
        "summary": (
            "El paciente inicia sesión en la página de autorización del proveedor y concede permisos seleccionados; "
            "HealthIA no almacena la contraseña."
        ),
        "patient_step": (
            "Selecciona Conectar Withings y aprueba los permisos solicitados en la página del proveedor."
        ),
    },
    {
        "id": "smart_on_fhir",
        "name": "Hospitales, laboratorios o aseguradoras",
        "platform": "FHIR / SMART on FHIR",
        "status": "planned_enterprise_adapter",
        "connection_mode": "oauth2_smart_on_fhir",
        "account_login": "organization_authorization_page",
        "requires_native_app": False,
        "summary": (
            "Los datos clínicos institucionales deben utilizar autorización estandarizada, acceso limitado y una "
            "importación auditable con procedencia."
        ),
        "patient_step": (
            "Selecciona la institución participante y autoriza los registros que HealthIA podrá importar."
        ),
    },
)


def health_data_provider_catalog() -> dict[str, Any]:
    providers = [dict(item) for item in PROVIDERS]
    return {
        "providers": providers,
        "implemented_count": sum(item["status"].startswith("implemented") for item in providers),
        "principle": (
            "HealthIA nunca solicita ni almacena contraseñas de Google, Samsung, Apple ni de proveedores de "
            "dispositivos. Las conexiones usan permisos del sistema operativo, tokens de vinculación o autorización "
            "OAuth alojada por el proveedor."
        ),
    }
