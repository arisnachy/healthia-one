# HealthIA ONE Continuity OS

Esta capa conecta datos que antes vivían separados: mediciones, peso, actividad, resultados, documentos, familia, tratamiento, citas, objetivos y misiones.

## Línea de salud

`build_timeline` genera una vista derivada y ordenada. No duplica los registros originales ni cambia su procedencia. Cada evento incluye:

- ID del objeto original;
- tipo;
- fecha;
- título;
- detalle;
- fuente.

La cronología puede incluir eventos futuros, como una cita programada, para que la continuidad abarque pasado, presente y próximo paso.

## Tratamiento y adherencia

HealthIA conserva el esquema exactamente como fue registrado:

- nombre;
- concentración;
- vía;
- frecuencia;
- propósito;
- instrucciones;
- profesional de origen;
- procedencia.

El paciente puede registrar una toma como `taken`, `late`, `skipped` o `unknown`. El porcentaje mostrado es **adherencia informada**, no una medición de absorción ni una autorización para modificar la dosis.

MEDSAFE nunca debe recomendar:

- duplicar una dosis;
- suspender un medicamento;
- cambiar frecuencia o concentración;
- sustituir un medicamento;
- compensar una omisión sin instrucciones profesionales.

## Citas y preparación

ADVOCATE prepara un resumen controlado por el paciente con:

- condiciones confirmadas;
- alergias;
- tratamiento activo;
- signos y peso recientes;
- resultados recientes;
- misiones abiertas;
- contexto familiar;
- documentos requeridos;
- preguntas prioritarias.

El paciente debe revisar el resumen antes de compartirlo. No es una nota clínica firmada.

## Condition Packs

Los paquetes iniciales son:

- hipertensión;
- seguimiento de peso.

Cada paquete declara señales y preguntas específicas. Los paquetes no ejecutan diagnóstico ni reemplazan protocolos profesionales; organizan qué información conviene registrar y discutir.

## Proactividad

El evaluador de continuidad está separado de las reglas clínicas deterministas. Puede detectar:

- una cita dentro de 72 horas;
- una toma omitida reportada.

Cada alerta incluye evidencia, razón pública, próximo paso y equipo de agentes. Las alertas son idempotentes mediante `emitted_rule_keys`.

## Chat como controlador

El chat puede abrir misiones para:

- tratamiento y tomas;
- preparación de consulta;
- línea de tiempo;
- familia;
- documentos;
- resultados;
- peso;
- presión;
- actividad.

Las respuestas incluyen `action_target`, que permite a la interfaz mostrar un botón contextual sin exponer razonamiento privado.

## Producción pendiente

Antes de procesar datos reales se requieren autenticación, autorización, cifrado, Cloud Storage privado, Firestore validado, auditoría, consentimiento granular, controles de retención, aislamiento multiusuario, revisión clínica y despliegue demostrado en Google Cloud.
