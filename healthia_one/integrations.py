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
            "HealthIA Bridge requests per-data-type Health Connect permissions on the phone and sends only "
            "authorized records to the paired HealthIA backend."
        ),
        "patient_step": "Install HealthIA Bridge, enter the backend address and six-digit code, then grant Health Connect permissions.",
    },
    {
        "id": "samsung_health_via_health_connect",
        "name": "Samsung Health / Galaxy Watch",
        "platform": "Samsung and Android",
        "status": "implemented_via_health_connect",
        "connection_mode": "samsung_health_to_health_connect_to_healthia",
        "account_login": "samsung_credentials_remain_inside_samsung_health",
        "requires_native_app": True,
        "summary": (
            "Samsung Health can write consented phone and Galaxy wearable data into Health Connect. The existing "
            "HealthIA Android bridge reads the resulting authorized records from Health Connect."
        ),
        "patient_step": "Enable Samsung Health synchronization with Health Connect, then grant HealthIA Bridge access in Health Connect.",
    },
    {
        "id": "samsung_health_data_sdk",
        "name": "Samsung Health Data SDK (direct)",
        "platform": "Android 10+",
        "status": "planned_optional_adapter",
        "connection_mode": "native_samsung_permission",
        "account_login": "not_shared_with_healthia",
        "requires_native_app": True,
        "summary": (
            "Optional direct adapter for Samsung-specific data not exposed through Health Connect. Public distribution "
            "requires Samsung partner registration and an approved package signature."
        ),
        "patient_step": "Grant selected Samsung Health data permissions in the native Android app when this adapter is released.",
    },
    {
        "id": "apple_healthkit",
        "name": "Apple Health / Apple Watch",
        "platform": "iPhone and Apple Watch",
        "status": "planned_native_ios_bridge",
        "connection_mode": "native_healthkit_permission",
        "account_login": "apple_id_not_shared_with_healthia",
        "requires_native_app": True,
        "summary": (
            "An iOS HealthIA Bridge must request fine-grained HealthKit authorization and upload only the samples "
            "the person permits. The web browser cannot read HealthKit directly."
        ),
        "patient_step": "Install the future HealthIA iOS bridge and approve the requested Health permissions on the iPhone.",
    },
    {
        "id": "fitbit",
        "name": "Fitbit",
        "platform": "Cloud account",
        "status": "planned_oauth_adapter",
        "connection_mode": "oauth2",
        "account_login": "provider_login_via_oauth",
        "requires_native_app": False,
        "summary": "The patient authorizes HealthIA through the provider OAuth screen; HealthIA never receives the password.",
        "patient_step": "Choose Connect Fitbit and approve the requested scopes on Fitbit's authorization page.",
    },
    {
        "id": "garmin",
        "name": "Garmin",
        "platform": "Cloud account",
        "status": "planned_partner_oauth_adapter",
        "connection_mode": "partner_api_oauth",
        "account_login": "provider_login_via_oauth",
        "requires_native_app": False,
        "summary": "A production adapter requires the provider program and consented cloud API access.",
        "patient_step": "Authorize the Garmin connection after HealthIA receives production API approval.",
    },
    {
        "id": "withings",
        "name": "Withings",
        "platform": "Cloud account",
        "status": "planned_oauth_adapter",
        "connection_mode": "oauth2",
        "account_login": "provider_login_via_oauth",
        "requires_native_app": False,
        "summary": "The patient signs in on the provider authorization page and grants selected scopes; passwords are not stored by HealthIA.",
        "patient_step": "Choose Connect Withings and approve the requested scopes on the provider page.",
    },
    {
        "id": "smart_on_fhir",
        "name": "Hospital or insurer records",
        "platform": "FHIR / SMART on FHIR",
        "status": "planned_enterprise_adapter",
        "connection_mode": "oauth2_smart_on_fhir",
        "account_login": "organization_authorization_page",
        "requires_native_app": False,
        "summary": "Institutional clinical data should use standards-based authorization, scoped access and auditable import.",
        "patient_step": "Select the participating institution and authorize the records HealthIA may import.",
    },
)


def health_data_provider_catalog() -> dict[str, Any]:
    providers = [dict(item) for item in PROVIDERS]
    return {
        "providers": providers,
        "implemented_count": sum(item["status"].startswith("implemented") for item in providers),
        "principle": (
            "HealthIA never asks for or stores Google, Samsung, Apple or wearable-provider passwords. "
            "Connections use operating-system permissions, pairing tokens or provider-hosted OAuth authorization."
        ),
    }
