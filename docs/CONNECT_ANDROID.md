# Conectar Android Health Connect con HealthIA ONE

HealthIA ONE no puede leer un reloj directamente desde el navegador. La conexión real utiliza un teléfono Android como puente:

```text
Reloj, báscula o tensiómetro
          ↓
Aplicación compatible / Health Connect
          ↓
HealthIA Android Bridge
          ↓
Servidor HealthIA ONE
```

## 1. Iniciar HealthIA

Para una prueba local desde la carpeta del proyecto:

```powershell
.\deployment\run-local-secure.ps1
```

El lanzador pide la clave de Gemini mediante entrada protegida, ejecuta una solicitud real mínima y muestra dos direcciones:

```text
Navegador en esta PC: http://127.0.0.1:8000
Teléfono en la misma Wi-Fi: http://192.168.x.x:8000
```

Para iniciar sin Google AI:

```powershell
.\deployment\run-local-secure.ps1 -Mock
```

El teléfono y la computadora deben estar en la misma red Wi-Fi. En el teléfono no funciona `127.0.0.1`; usa la dirección LAN impresa por el lanzador. También puedes encontrarla con `ipconfig` buscando **Dirección IPv4** en el adaptador Wi-Fi activo.

Para la prueba FCM LIVE del hackathon, el bridge debe apuntar al endpoint HealthIA controlado que tenga desplegados `/api/devices/fcm/register` y `/api/devices/fcm/ack`; un APK conectado a un backend antiguo no puede producir la evidencia de entrega completa.

## 2. Obtener la aplicación Android

El workflow **Android bridge compile + FCM-ready APK** separa dos estados que no deben confundirse:

- **Android CODE PASS**: el código compila correctamente.
- **FCM-READY APK**: además de compilar, el build contiene una configuración Firebase válida para el proyecto HealthIA controlado.

Cada ejecución publica el artefacto de evidencia:

```text
HealthIA-Android-APK-Readiness
```

Si su `status.json` indica `BLOCKED_FIREBASE_CONFIG`, el código Android puede estar verde pero **no existe un APK válido para probar FCM**. En ese estado el workflow elimina el APK compilado y no publica `HealthIA-Bridge-debug`.

Solo cuando están configurados de forma segura estos cuatro valores en GitHub Actions:

```text
HEALTHIA_FIREBASE_APP_ID
HEALTHIA_FIREBASE_API_KEY
HEALTHIA_FIREBASE_PROJECT_ID
HEALTHIA_FIREBASE_SENDER_ID
```

el workflow verifica que el `BuildConfig` generado no tenga identificadores vacíos y publica:

```text
HealthIA-Bridge-debug
```

El artefacto es un ZIP. Extráelo para obtener:

```text
HealthIA-Bridge-debug.apk
```

No copies esos valores a logs, issues, PRs ni artefactos de evidencia. El workflow los consume desde GitHub Actions y los enmascara durante el build.

También puedes abrir `android-health-bridge` en Android Studio y ejecutar la aplicación directamente en un teléfono, pero una prueba FCM real sigue requiriendo la configuración Firebase válida.

> El APK de depuración sirve para pruebas controladas del hackathon. Una distribución pública requiere firma de release, política de privacidad, HTTPS, cuentas autenticadas y revisión de permisos.

## 3. Generar el código de conexión

En HealthIA ONE:

1. Abre **Dispositivos**.
2. Pulsa **Conectar teléfono o reloj**.
3. Revisa la dirección del servidor.
4. Copia el código temporal de ocho dígitos.

El código es temporal y solo puede reclamarse una vez. El bearer final del dispositivo nunca se muestra en la web; queda vinculado al paciente, la conexión y el identificador del dispositivo. Si la conexión se revoca, el backend rechaza las operaciones posteriores de ese dispositivo.

La variante `debug` admite HTTP solo para pruebas sintéticas en una red local confiable. La variante de producción exige HTTPS y deshabilita tráfico en texto claro.

## 4. Vincular el teléfono

En **HealthIA Android Bridge**:

1. Escribe la dirección del servidor HealthIA.
2. Escribe el código temporal de ocho dígitos.
3. Pulsa **Vincular con HealthIA**.
4. Autoriza notificaciones cuando Android lo solicite.
5. Instala o actualiza Health Connect si la aplicación lo solicita.
6. Pulsa **Autorizar datos en Health Connect**.
7. Concede únicamente los tipos que desees compartir.
8. Pulsa **Sincronizar ahora** si quieres enviar datos de Health Connect.

Tras vincularse, el bridge solicita a Firebase su registration token y lo envía al endpoint firmado `/api/devices/fcm/register`. El token no debe copiarse manualmente ni aparecer en GitHub, logs o artefactos.

Cuando Firebase rote ese token, `HealthiaFirebaseMessagingService.onNewToken()` vuelve a registrar el nuevo valor automáticamente.

## 5. Prueba FCM LIVE controlada

El gate FCM no considera suficiente que Google acepte un mensaje.

La prueba completa es:

```text
registro real del Android
        ↓
1 mensaje FCM data-only, PHI-neutral
        ↓
Android recibe kind=healthia_update + proof_id
        ↓
notificación local fija, sin texto clínico enviado por servidor
        ↓
Android firma ACK al backend
        ↓
Firestore conserva proof_id + timestamp
        ↓
LIVE PASS
```

El texto visible está fijado dentro de la aplicación:

```text
HealthIA
Tienes una actualización disponible en HealthIA.
```

El `proof_id` es evidencia operativa sintética; no contiene diagnóstico, resultado, medicamento, nombre de paciente ni otro contenido clínico.

## 6. De dónde salen los datos

El puente lee registros que ya estén presentes en Health Connect:

- pasos y pulso: teléfono, reloj o aplicación compatible;
- peso: báscula compatible o entrada desde una aplicación;
- presión arterial: tensiómetro o aplicación que escriba presión;
- IMC: lo calcula HealthIA con peso y talla;
- glucosa: glucómetro, monitor continuo o aplicación compatible;
- colesterol: normalmente llega desde laboratorio o expediente, no desde un reloj común.

## 7. Disponibilidad de Health Connect

El puente comprueba el estado antes de crear el cliente:

- si está disponible, permite solicitar permisos;
- si falta o requiere actualización, abre Google Play;
- si el teléfono no es compatible, no intenta leer registros;
- la lectura en segundo plano se solicita solo cuando la función existe.

## 8. Sincronización en segundo plano

La lectura en segundo plano se activa únicamente cuando el teléfono y Health Connect ofrecen esa función y el paciente concede el permiso. Android puede retrasar el trabajo periódico para ahorrar batería, por lo que no debe presentarse como una transmisión clínica garantizada en tiempo real.

## 9. Probar sin hardware

En **Dispositivos**, pulsa **Probar sin dispositivo**. Esa ruta carga datos sintéticos para verificar la interfaz, tendencias y cruces de continuidad. No demuestra que un reloj físico esté conectado ni sustituye la prueba FCM con un Android real.
