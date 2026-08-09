# Conectar Android Health Connect con HealthIA ONE

HealthIA ONE no puede leer un reloj directamente desde el navegador. La conexión real utiliza un teléfono Android como puente:

```text
Reloj, báscula o tensiómetro
          ↓
Aplicación compatible / Health Connect
          ↓
HealthIA Android Bridge
          ↓
Servidor local HealthIA ONE
```

## 1. Iniciar HealthIA en la computadora

Desde la carpeta del proyecto:

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

## 2. Obtener la aplicación Android

Abre el workflow **Android bridge APK** en GitHub Actions, entra en la ejecución más reciente y descarga el artefacto:

```text
HealthIA-Bridge-debug
```

El artefacto es un ZIP. Extráelo para obtener:

```text
HealthIA-Bridge-debug.apk
```

También puedes abrir `android-health-bridge` en Android Studio y ejecutar la aplicación directamente en un teléfono.

> El APK de depuración sirve para pruebas del hackathon. Una distribución pública requiere firma de release, política de privacidad, HTTPS, cuentas autenticadas y revisión de permisos.

## 3. Generar el código de conexión

En HealthIA ONE:

1. Abre **Dispositivos**.
2. Pulsa **Conectar teléfono o reloj**.
3. Revisa la dirección LAN del servidor.
4. Copia el código temporal de ocho dígitos.

El código dura cinco minutos y solo puede reclamarse una vez. El token final del dispositivo nunca se muestra en la web. Es una credencial HMAC firmada y vinculada al paciente, conexión y dispositivo; no se persiste su hash. La desconexión marca la conexión como revocada y el backend rechaza nuevos lotes con esa credencial.

La variante `debug` admite HTTP solo para pruebas sintéticas en una red local confiable. La variante de producción exige HTTPS y deshabilita tráfico en texto claro.

## 4. Vincular el teléfono

En **HealthIA Android Bridge**:

1. Escribe la dirección LAN del servidor HealthIA.
2. Escribe el código temporal de ocho dígitos.
3. Pulsa **Vincular con HealthIA**.
4. Instala o actualiza Health Connect si la aplicación lo solicita.
5. Pulsa **Autorizar datos en Health Connect**.
6. Concede únicamente los tipos que desees compartir.
7. Pulsa **Sincronizar ahora**.

HealthIA mostrará el teléfono como conectado y actualizará los registros recibidos.

## 5. De dónde salen los datos

El puente lee registros que ya estén presentes en Health Connect:

- pasos y pulso: teléfono, reloj o aplicación compatible;
- peso: báscula compatible o entrada desde una aplicación;
- presión arterial: tensiómetro o aplicación que escriba presión;
- IMC: lo calcula HealthIA con peso y talla;
- glucosa: glucómetro, monitor continuo o aplicación compatible;
- colesterol: normalmente llega desde laboratorio o expediente, no desde un reloj común.

## 6. Disponibilidad de Health Connect

El puente comprueba el estado antes de crear el cliente:

- si está disponible, permite solicitar permisos;
- si falta o requiere actualización, abre Google Play;
- si el teléfono no es compatible, no intenta leer registros;
- la lectura en segundo plano se solicita solo cuando la función existe.

## 7. Sincronización en segundo plano

La lectura en segundo plano se activa únicamente cuando el teléfono y Health Connect ofrecen esa función y el paciente concede el permiso. Android puede retrasar el trabajo periódico para ahorrar batería, por lo que no debe presentarse como una transmisión clínica garantizada en tiempo real.

## 8. Probar sin hardware

En **Dispositivos**, pulsa **Probar sin dispositivo**. Esa ruta carga datos sintéticos para verificar la interfaz, tendencias y cruces de continuidad. No demuestra que un reloj físico esté conectado.
