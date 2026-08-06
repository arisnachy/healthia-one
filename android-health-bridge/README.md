# HealthIA Android Health Bridge

Android companion source for reading authorized records from Health Connect and sending idempotent batches to HealthIA ONE.

## Scope

- Health Connect 1.1.0 stable.
- Steps, heart rate, blood pressure, weight, height, oxygen saturation, respiratory rate, body temperature, blood glucose, and menstruation periods.
- Background reads through Health Connect permission plus WorkManager.
- Provenance: Health Connect metadata, package, device, recording method, and external record ID.
- No silent access: the patient grants each permission and may pause or revoke access.

## Obtain the test app

Every verified Android bridge workflow run builds the `HealthIA-Bridge-debug` artifact. Download its `HealthIA-Bridge-debug.apk` for an unsigned development installation, or open this folder in Android Studio and build the `app` module. The debug APK is for testing only; it is not a signed production release.

## Connect a phone

1. Start HealthIA ONE with `deployment/run-local-secure.ps1`. The launcher prints both the local browser address and the LAN address for a phone on the same Wi-Fi.
2. Open **Dispositivos → Conectar dispositivo** in the web interface.
3. Install the debug bridge on Android 9+ or run it in an emulator.
4. In the bridge, enter the backend address and the six-digit code shown by HealthIA.
   - Emulator: `http://10.0.2.2:8000`.
   - Physical phone: use the `http://<LAN-IP-OF-THE-PC>:8000` address printed by the launcher. `127.0.0.1` points to the phone itself and will not work.
5. Tap **Pair with HealthIA**, grant the requested Health Connect permissions, then tap **Sync now**.
6. After the first successful sync, WorkManager schedules background synchronization at Android's permitted cadence.

The six-digit code expires after ten minutes. The device token remains valid for the lifetime of the local server process; reconnect after restarting the backend. Use HTTPS, authenticated patient accounts and encrypted token storage in production.

## Important boundary

Health Connect is a synchronization store, not a guaranteed continuous clinical stream. A metric exists only when a compatible device or source app writes it. Cholesterol is not a core consumer Health Connect record in this bridge; HealthIA receives it from structured laboratory results or a future FHIR/medical-record integration.

A real-device run is still required before claiming physical hardware validation.
