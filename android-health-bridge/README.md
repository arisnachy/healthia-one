# HealthIA Android Health Bridge

Aplicación complementaria para leer registros autorizados de Health Connect y enviar lotes idempotentes a HealthIA ONE.

## Alcance

- Health Connect 1.1.0 estable.
- Pasos, frecuencia cardiaca, presión arterial, peso, talla, saturación, frecuencia respiratoria, temperatura corporal, glucosa y períodos menstruales.
- Lectura en segundo plano solo cuando Health Connect ofrece la función y el paciente concede el permiso.
- Procedencia: paquete de origen, dispositivo, fabricante, modelo, método de registro e identificador externo.
- Sin acceso silencioso: el paciente concede cada permiso y puede revocarlo.

## Obtener la aplicación de prueba

Cada ejecución del workflow **Android bridge APK** construye el artefacto:

```text
HealthIA-Bridge-debug
```

Descarga el artefacto desde GitHub Actions y extrae `HealthIA-Bridge-debug.apk`, o abre esta carpeta en Android Studio y ejecuta el módulo `app`.

El APK de depuración sirve para pruebas del hackathon; no es una distribución pública firmada.

## Conectar un teléfono

1. Inicia HealthIA ONE con `deployment/run-local-secure.ps1`.
2. El lanzador imprime la dirección del navegador y una o más direcciones LAN para el teléfono.
3. Abre **Dispositivos → Conectar teléfono o reloj**.
4. Instala y abre HealthIA Bridge.
5. En el puente escribe la dirección LAN y el código de seis dígitos.
   - Emulador: `http://10.0.2.2:8000`.
   - Teléfono físico: `http://<IP-LAN-DE-LA-PC>:8000`.
   - `127.0.0.1` en el teléfono apunta al propio teléfono y no funciona.
6. Pulsa **Vincular con HealthIA**.
7. Instala o actualiza Health Connect si la app lo solicita.
8. Pulsa **Autorizar datos en Health Connect** y elige qué compartir.
9. Pulsa **Sincronizar ahora**.

El código temporal expira después de diez minutos. El token del dispositivo permanece válido durante el proceso local del servidor; vuelve a vincular tras reiniciar el backend.

## Disponibilidad y segundo plano

El puente comprueba `HealthConnectClient.getSdkStatus` antes de crear el cliente. Si el proveedor falta o necesita actualización, ofrece abrir Google Play. La lectura en segundo plano solo se solicita cuando `FEATURE_READ_HEALTH_DATA_IN_BACKGROUND` está disponible; de lo contrario, la sincronización sigue funcionando manualmente.

## Límite importante

Health Connect es un almacén de sincronización, no una transmisión clínica continua garantizada. Una métrica existe solo si un reloj, báscula, tensiómetro, teléfono o aplicación compatible la escribe.

Consulta `docs/CONNECT_ANDROID.md` para la guía completa. La validación con teléfono y reloj físicos sigue siendo obligatoria antes de declarar hardware comprobado.
