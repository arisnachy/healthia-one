# HealthIA Android Health Bridge

Aplicación complementaria para leer registros autorizados de Health Connect y enviar lotes idempotentes a HealthIA ONE.

## Alcance

- Health Connect 1.1.0 estable.
- Pasos, frecuencia cardiaca, presión arterial, peso, talla, saturación, frecuencia respiratoria, temperatura corporal, glucosa y períodos menstruales.
- Lectura en segundo plano solo cuando Health Connect ofrece la función y el paciente concede el permiso.
- Procedencia: paquete de origen, dispositivo, fabricante, modelo, método de registro e identificador externo.
- Sin acceso silencioso: Android muestra los permisos y el paciente puede revocarlos.

## Obtener la aplicación

El workflow permanente **Android bridge APK** compila la aplicación y publica el artefacto:

```text
HealthIA-Bridge-debug
```

Abre GitHub Actions, entra en la ejecución más reciente del workflow y descarga el artefacto. Extrae el ZIP para obtener `HealthIA-Bridge-debug.apk`.

También puedes abrir esta carpeta en Android Studio y ejecutar la app en un teléfono compatible.

## Conectar un teléfono

1. Inicia HealthIA ONE con `deployment/run-local-secure.ps1`.
2. Abre **Dispositivos → Conectar teléfono o reloj**.
3. Instala y abre **HealthIA Android Bridge**.
4. En el puente, escribe la dirección y el código de seis dígitos mostrados por HealthIA.
   - Emulador: `http://10.0.2.2:8000`.
   - Teléfono físico: `http://<IP-LAN-DE-LA-PC>:8000`.
   - `127.0.0.1` en el teléfono apunta al propio teléfono y no funciona.
5. Pulsa **Vincular con HealthIA**.
6. Pulsa **Autorizar datos en Health Connect** y elige qué compartir.
7. Pulsa **Sincronizar ahora**.

El código temporal expira después de diez minutos y solo puede reclamarse una vez. El token del dispositivo permanece válido mientras el servidor local esté encendido; vuelve a vincular después de reiniciar el backend.

## Disponibilidad de Health Connect

El puente comprueba el estado antes de crear el cliente:

- si está disponible, permite solicitar permisos;
- si falta o requiere actualización, ofrece abrir Google Play;
- si el teléfono no lo soporta, no intenta leer registros;
- la lectura en segundo plano se activa únicamente cuando la función existe.

La aplicación también incluye una pantalla de explicación del uso de los datos para el flujo de permisos de Health Connect.

## Límites importantes

Health Connect es una capa de sincronización, no una transmisión clínica continua garantizada. Una métrica existe solo cuando un reloj, báscula, tensiómetro, teléfono o aplicación compatible la escribe.

El artefacto de Actions es un APK de depuración para pruebas del hackathon. Una distribución pública requiere firma de release, política de privacidad, HTTPS, cuentas autenticadas y almacenamiento cifrado del token.

Consulta `docs/CONNECT_ANDROID.md` para la guía completa.
