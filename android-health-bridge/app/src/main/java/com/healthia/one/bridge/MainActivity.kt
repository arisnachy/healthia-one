package com.healthia.one.bridge

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID

class MainActivity : ComponentActivity() {
    private lateinit var repository: HealthConnectRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        repository = HealthConnectRepository(this)
        val preferences = getSharedPreferences("healthia", MODE_PRIVATE)
        setContent {
            MaterialTheme {
                BridgeScreen(
                    permissions = repository.permissions,
                    dataPermissions = repository.dataPermissions,
                    healthConnectAvailable = repository.isAvailable,
                    providerUpdateRequired = repository.providerUpdateRequired,
                    supportsBackgroundRead = repository.supportsBackgroundRead,
                    availabilityMessage = repository.availabilityMessage(),
                    initialBaseUrl = preferences.getString("base_url", BuildConfig.HEALTHIA_BASE_URL).orEmpty(),
                    initialNotificationsEnabled = FirebaseRuntime.notificationsEnabled(this),
                    connect = { baseUrl, code, updateStatus -> connectBridge(baseUrl, code, updateStatus) },
                    syncNow = { updateStatus -> syncNow(updateStatus) },
                    setPrivateNotifications = { enabled, complete -> setPrivateNotifications(enabled, complete) },
                    installOrUpdate = ::installOrUpdateHealthConnect,
                    openHealthConnect = ::openHealthConnect,
                )
            }
        }
        // If this device was already paired, refresh its FCM token mapping on each
        // foreground launch only while the user has private notifications enabled.
        FirebaseRuntime.syncRegistration(applicationContext)
    }

    private fun connectBridge(baseUrl: String, code: String, updateStatus: (String) -> Unit) {
        lifecycleScope.launch {
            updateStatus("Conectando con HealthIA…")
            runCatching {
                val normalizedUrl = baseUrl.trim().trimEnd('/')
                val scheme = Uri.parse(normalizedUrl).scheme?.lowercase()
                require(scheme == "https" || (BuildConfig.DEBUG && scheme == "http")) {
                    "La versión de producción exige HTTPS. HTTP solo está permitido en la compilación de demostración local."
                }
                val token = withContext(Dispatchers.IO) {
                    HealthiaApi.claim(normalizedUrl, code, deviceId(), "HealthIA Android Bridge")
                }
                getSharedPreferences("healthia", MODE_PRIVATE).edit()
                    .putString("base_url", normalizedUrl)
                    .putString("access_token", token)
                    .apply()
                if (FirebaseRuntime.notificationsEnabled(applicationContext)) {
                    requestNotificationPermissionIfNeeded()
                    FirebaseRuntime.syncRegistration(applicationContext)
                    updateStatus("Teléfono vinculado. Registrando notificaciones privadas; autoriza Health Connect cuando quieras sincronizar datos.")
                } else {
                    updateStatus("Teléfono vinculado. Tus notificaciones privadas siguen desactivadas hasta que las reactives explícitamente.")
                }
            }.onFailure { updateStatus("No se pudo vincular: ${it.message}") }
        }
    }

    private fun setPrivateNotifications(enabled: Boolean, complete: (Boolean, String) -> Unit) {
        val preferences = getSharedPreferences("healthia", MODE_PRIVATE)
        val baseUrl = preferences.getString("base_url", "").orEmpty()
        val accessToken = preferences.getString("access_token", "").orEmpty()
        val currentDeviceId = preferences.getString("device_id", "").orEmpty()
        if (baseUrl.isBlank() || accessToken.isBlank() || currentDeviceId.isBlank()) {
            complete(FirebaseRuntime.notificationsEnabled(applicationContext), "Vincula el teléfono con HealthIA antes de cambiar las notificaciones privadas.")
            return
        }

        if (!enabled) {
            lifecycleScope.launch {
                runCatching {
                    withContext(Dispatchers.IO) {
                        HealthiaApi.disableFcm(baseUrl, accessToken, currentDeviceId)
                    }
                }.onSuccess {
                    FirebaseRuntime.setNotificationsEnabled(applicationContext, false)
                    complete(false, "Notificaciones privadas desactivadas. HealthIA no volverá a registrar este teléfono automáticamente.")
                }.onFailure {
                    complete(true, "No se pudieron desactivar las notificaciones: ${it.message}")
                }
            }
            return
        }

        if (!FirebaseRuntime.initialize(applicationContext)) {
            complete(false, "Firebase no está configurado en esta compilación; no se pueden reactivar las notificaciones.")
            return
        }
        requestNotificationPermissionIfNeeded()
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { registrationToken ->
                if (registrationToken.isBlank()) {
                    complete(false, "Firebase no devolvió un token válido; las notificaciones siguen desactivadas.")
                    return@addOnSuccessListener
                }
                lifecycleScope.launch {
                    runCatching {
                        withContext(Dispatchers.IO) {
                            HealthiaApi.explicitlyEnableFcm(
                                baseUrl,
                                accessToken,
                                currentDeviceId,
                                registrationToken,
                            )
                        }
                    }.onSuccess {
                        FirebaseRuntime.setNotificationsEnabled(applicationContext, true)
                        FirebaseRuntime.syncRegistration(applicationContext)
                        complete(true, "Notificaciones privadas reactivadas explícitamente.")
                    }.onFailure {
                        complete(false, "No se pudieron reactivar las notificaciones: ${it.message}")
                    }
                }
            }
            .addOnFailureListener {
                complete(false, "No se pudo obtener el token de Firebase; las notificaciones siguen desactivadas.")
            }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 42001)
        }
    }

    private fun syncNow(updateStatus: (String) -> Unit) {
        lifecycleScope.launch {
            updateStatus("Sincronizando…")
            runCatching {
                check(repository.isAvailable) { repository.availabilityMessage() }
                val preferences = getSharedPreferences("healthia", MODE_PRIVATE)
                val baseUrl = preferences.getString("base_url", "").orEmpty()
                val token = preferences.getString("access_token", "").orEmpty()
                require(baseUrl.isNotBlank() && token.isNotBlank()) { "Vincula el puente primero" }
                val records = repository.readSince()
                val grantedMetrics = repository.grantedMetricNames()
                withContext(Dispatchers.IO) {
                    HealthiaApi.sync(
                        baseUrl,
                        token,
                        deviceId(),
                        records,
                        background = false,
                        grantedMetrics = grantedMetrics,
                    )
                }
                if (repository.supportsBackgroundRead) {
                    HealthSyncWorker.schedule(this@MainActivity)
                }
                updateStatus("Sincronización completada: ${records.size} registros")
            }.onFailure { updateStatus("No se pudo sincronizar: ${it.message}") }
        }
    }

    private fun installOrUpdateHealthConnect() {
        try {
            startActivity(repository.providerInstallIntent())
        } catch (_: ActivityNotFoundException) {
            startActivity(
                Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse("https://play.google.com/store/apps/details?id=com.google.android.apps.healthdata"),
                )
            )
        }
    }

    private fun openHealthConnect() {
        runCatching { startActivity(repository.manageDataIntent()) }
            .onFailure { installOrUpdateHealthConnect() }
    }

    private fun deviceId(): String {
        val preferences = getSharedPreferences("healthia", MODE_PRIVATE)
        return preferences.getString("device_id", null) ?: UUID.randomUUID().toString().also {
            preferences.edit().putString("device_id", it).apply()
        }
    }
}

@Composable
private fun BridgeScreen(
    permissions: Set<String>,
    dataPermissions: Set<String>,
    healthConnectAvailable: Boolean,
    providerUpdateRequired: Boolean,
    supportsBackgroundRead: Boolean,
    availabilityMessage: String,
    initialBaseUrl: String,
    initialNotificationsEnabled: Boolean,
    connect: (String, String, (String) -> Unit) -> Unit,
    syncNow: ((String) -> Unit) -> Unit,
    setPrivateNotifications: (Boolean, (Boolean, String) -> Unit) -> Unit,
    installOrUpdate: () -> Unit,
    openHealthConnect: () -> Unit,
) {
    var status by remember { mutableStateOf(availabilityMessage) }
    var baseUrl by remember { mutableStateOf(initialBaseUrl) }
    var code by remember { mutableStateOf("") }
    var notificationsEnabled by remember { mutableStateOf(initialNotificationsEnabled) }
    val permissionLauncher = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status = if (granted.any { it in dataPermissions }) {
            "Permisos actualizados. HealthIA solo leerá los tipos autorizados."
        } else {
            "No concediste tipos de datos. Elige al menos uno para sincronizar."
        }
    }

    Surface(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("HealthIA Android Bridge", style = MaterialTheme.typography.headlineSmall)
            Text("Conecta Health Connect con tu servidor HealthIA mediante una dirección segura y un código temporal.")

            AssistChip(
                onClick = {},
                enabled = false,
                label = { Text(availabilityMessage) },
            )

            if (!healthConnectAvailable) {
                Text(
                    if (providerUpdateRequired) {
                        "Instala o actualiza Health Connect antes de solicitar permisos."
                    } else {
                        "Este teléfono no ofrece Health Connect. Se requiere un Android compatible con Google Play."
                    }
                )
                Button(onClick = installOrUpdate) { Text("Instalar o actualizar Health Connect") }
            }

            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                label = { Text("Dirección del servidor HealthIA") },
                supportingText = {
                    Text("Usa HTTPS para Cloud. En demo local: http://192.168.1.25:8000; no uses 127.0.0.1 en el teléfono.")
                },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = code,
                onValueChange = { code = it.filter(Char::isDigit).take(8) },
                label = { Text("Código temporal de ocho dígitos") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            Text(status)

            Button(
                enabled = baseUrl.isNotBlank() && code.length == 8,
                onClick = { connect(baseUrl, code) { status = it } },
            ) { Text("Vincular con HealthIA") }

            Text(
                if (notificationsEnabled) {
                    "Notificaciones privadas: activadas. Los avisos no incluyen contenido clínico."
                } else {
                    "Notificaciones privadas: desactivadas. El teléfono no se volverá a registrar automáticamente."
                }
            )
            OutlinedButton(
                onClick = {
                    setPrivateNotifications(!notificationsEnabled) { actual, message ->
                        notificationsEnabled = actual
                        status = message
                    }
                },
            ) {
                Text(if (notificationsEnabled) "Desactivar notificaciones privadas" else "Reactivar notificaciones privadas")
            }

            OutlinedButton(
                enabled = healthConnectAvailable,
                onClick = { permissionLauncher.launch(permissions) },
            ) { Text("Autorizar datos en Health Connect") }

            OutlinedButton(
                enabled = healthConnectAvailable,
                onClick = openHealthConnect,
            ) { Text("Abrir configuración de Health Connect") }

            OutlinedButton(
                enabled = healthConnectAvailable,
                onClick = { syncNow { status = it } },
            ) { Text("Sincronizar ahora") }

            Text(
                if (supportsBackgroundRead) {
                    "Tras una sincronización correcta, Android puede revisar cambios en segundo plano. No es una transmisión clínica en tiempo real."
                } else {
                    "Este teléfono no ofrece lectura en segundo plano; abre la app y pulsa Sincronizar ahora para actualizar los datos."
                }
            )
        }
    }
}
