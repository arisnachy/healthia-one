from healthia_one.devices import device_summary
from healthia_one.integrations import health_data_provider_catalog
from healthia_one.service import seed_state


def test_provider_catalog_never_asks_for_platform_passwords() -> None:
    catalog = health_data_provider_catalog()
    providers = {item["id"]: item for item in catalog["providers"]}

    assert catalog["implemented_count"] == 1
    assert "nunca solicita ni almacena contraseñas" in catalog["principle"]
    assert providers["android_health_connect"]["status"] == "implemented"
    assert providers["samsung_health_via_health_connect"]["status"] == "available_via_health_connect_unverified_hardware"
    assert providers["apple_healthkit"]["status"] == "planned_native_ios_bridge"
    assert providers["apple_healthkit"]["account_login"] == "apple_id_not_shared_with_healthia"
    assert providers["fitbit"]["connection_mode"] == "oauth2"


def test_device_summary_exposes_provider_catalog() -> None:
    summary = device_summary(seed_state())
    assert summary["provider_catalog"]["providers"]
    assert summary["provider_catalog"]["implemented_count"] == 1
