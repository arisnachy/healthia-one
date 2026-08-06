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

El lanzador pedirá la clave de Gemini mediante entrada protegida y abrirá HealthIA en el puerto 8000. Para usar el sistema sin Google AI:

```powershell
.\deployment\run-local-secure.ps1 -Mock
```

El teléfono y la computadora deben estar en la misma red Wi‑Fi. En el teléfono no funciona `127.0.0.1`; usa la dirección IPv4 local de la computadora, por ejemplo:

```text
http://192.168.1.25:8000
```

En Windows puedes encontrarla con:

```powershell
ipconfig
```

Busca **Dirección IPv4** en el adaptador Wi‑Fi activo.

## 2. Obtener la aplicación Android

Abre el workflow **Android bridge APK** en GitHub Actions, entra en la ejecución correcta y descarga el artefacto:

```text
HealthIA-Bridge-debug
```

El artefacto es un ZIP. Extráelo para obtener:

```text
HealthIA-Bridge-debug.apk
```

También puedes abrir la carpeta `android-health-bridge` en Android Studio y ejecutar la aplicación directamente en un teléfono.

> El APK de depuración sirve para pruebas del hackathon. Una distribución pública requiere firma de release, política de privacidad y revisión de permisos.

## 3. Generar el código de conexión

En HealthIA ONE:

1. Abre **Dispositivos**.
2. Pulsa **Conectar teléfono o reloj**.
3. Revisa o corrige la dirección del servidor.
4. Copia el código temporal de seis dígitos.

El código dura diez minutos y solo puede reclamarse una vez. El token final del dispositivo nunca se muestra en la web y el servidor conserva únicamente su hash.

## 4. Vincular el teléfono

En **HealthIA Android Bridge**:

1. Escribe la dirección del servidor HealthIA.
2. Escribe el código de seis dígitos.
3. Pulsa **Vincular con HealthIA**.
4. Pulsa **Autorizar datos en Health Connect**.
5. Concede únicamente los tipos que desees compartir.
6. Pulsa **Sincronizar ahora**.

HealthIA mostrará el teléfono como conectado y actualizará los registros recibidos.

## 5. De dónde salen los datos

El puente lee registros que ya estén presentes en Health Connect. Por tanto:

- los pasos y el pulso pueden venir del teléfono o reloj;
- el peso suele venir de una báscula compatible o de una aplicación;
- la presión requiere un tensiómetro o una aplicación que escriba presión en Health Connect;
- el IMC lo calcula HealthIA usando peso y talla;
- la glucosa requiere un glucómetro, monitor continuo o aplicación compatible;
- el colesterol suele llegar desde laboratorio o expediente, no desde un reloj común.

## 6. Qué hacer si Health Connect no aparece

La aplicación puente comprueba su disponibilidad:

- en Android moderno puede estar integrado en el sistema;
- en Android 13 o anterior puede requerir la aplicación Health Connect de Google Play;
- algunos teléfonos no compatibles no permiten usarlo.

Cuando sea necesario, el puente mostrará **Instalar o actualizar Health Connect**.

## 7. Sincronización en segundo plano

La lectura en segundo plano solo se activa cuando el teléfono y Health Connect ofrecen esa función y el paciente concede el permiso correspondiente. Android puede retrasar el trabajo periódico para ahorrar batería, por lo que no debe presentarse como una transmisión clínica garantizada en tiempo real.

## 8. Probar sin hardware

En la pantalla **Dispositivos**, pulsa **Probar sin dispositivo**. Esa ruta carga datos sintéticos para verificar la interfaz, tendencias y cruces de continuidad. No demuestra que un reloj físico esté conectado.
