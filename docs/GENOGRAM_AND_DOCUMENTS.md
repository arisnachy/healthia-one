# Genograma patológico y archivo documental

HealthIA ONE organiza antecedentes familiares y documentos dentro del expediente longitudinal del paciente. Estas funciones están centradas en continuidad, procedencia y preparación de próximos pasos; no convierten el producto en un sistema de diagnóstico autónomo.

## Genograma patológico

Cada familiar registra:

- parentesco y etiqueta visible;
- generación;
- línea materna, paterna, ambas o desconocida;
- sexo al nacer cuando el paciente decide registrarlo;
- relación biológica o no biológica;
- patologías reportadas;
- edad aproximada al diagnóstico;
- estado confirmado o no confirmado;
- notas y procedencia.

HEREDITAS agrupa condiciones normalizadas cuando existen dos o más familiares biológicos afectados o un registro de inicio temprano. Una agrupación produce una **pregunta preventiva**, no una conclusión clínica.

El sistema debe decir expresamente:

> Los patrones familiares aportan contexto y preguntas de prevención; no determinan que el paciente tenga o desarrollará una enfermedad.

Los familiares no biológicos pueden conservarse como parte de la red de apoyo, pero no participan en la detección de agregación biológica.

## Archivo documental

ARCHIVUM organiza:

- laboratorios;
- imágenes e informes radiológicos;
- recetas;
- notas de consulta;
- documentos de alta;
- vacunas;
- seguro;
- identidad;
- otros archivos autorizados.

Cada documento conserva:

- ID estable;
- nombre original saneado;
- título;
- categoría;
- tipo MIME;
- tamaño;
- fecha de carga;
- ruta de almacenamiento;
- estado de revisión;
- resumen;
- etiquetas;
- procedencia.

La aplicación acepta JSON, CSV, TXT, PDF, PNG y JPEG hasta el límite configurado. Los PDF e imágenes quedan en `pending_review` cuando no existe una extracción multimodal verificable. HealthIA no inventa texto ni resultados de archivos que no pudo leer.

## Chat como controlador

El paciente puede escribir solicitudes como:

- “Muéstrame mi genograma”.
- “¿Qué antecedentes familiares tengo registrados?”.
- “Organiza mis documentos del expediente”.
- “Quiero cargar una receta”.

KIRA selecciona el equipo mínimo:

- HEREDITAS + HISTORIA + SENTINEL para familia;
- ARCHIVUM + HISTORIA + LUMEN para documentación;
- NAVIGATOR cuando existe seguimiento;
- KIRA para integrar, exponer incertidumbre y definir la siguiente acción.

La interfaz mantiene accesos directos desde el compositor y añade botones contextuales a las respuestas del chat.

## Persistencia

Los nuevos objetos forman parte de `PatientState` y funcionan con los adaptadores existentes:

- MemoryStore para pruebas;
- JsonStore para demostración local;
- FirestoreStore como frontera de despliegue.

En producción, los archivos binarios deben migrarse a Cloud Storage con acceso autenticado y referencias firmadas; Firestore conserva metadatos, misiones y procedencia. La implementación local guarda archivos en `uploads/patient_demo`, una ruta excluida de Git.

## Seguridad y privacidad pendientes para producción

Antes de usar datos reales se requiere:

- autenticación del paciente;
- autorización por recurso;
- cifrado y retención;
- consentimiento granular para historia familiar;
- registro de acceso;
- eliminación y exportación del paciente;
- malware scanning;
- Cloud Storage privado;
- revisión legal y clínica;
- pruebas de aislamiento entre pacientes.

La demostración pública del hackathon utiliza únicamente datos sintéticos.
