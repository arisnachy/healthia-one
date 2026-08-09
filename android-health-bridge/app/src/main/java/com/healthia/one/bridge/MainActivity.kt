package com.healthia.one.bridge

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
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
                    connect = { baseUrl, code, updateStatus -> connectBridge(baseUrl, code, updateStatus) },
                    syncNow = { updateStatus -> syncNow(updateStatus) },
                    installOrUpdate = ::installOrUpdateHealthConnect,
                    openHealthConnect = ::openHealthConnect,
                )
            }
        }
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
                updateStatus("Teléfono vinculado. Autoriza Health Connect y pulsa Sincronizar ahora.")
            }.onFailure { updateStatus("No se pudo vincular: ${it.message}") }
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
    connect: (String, String, (String) -> Unit) -> Unit,
    syncNow: ((String) -> Unit) -> Unit,
    installOrUpdate: () -> Unit,
    openHealthConnect: () -> Unit,
) {
    var status by remember { mutableStateOf(availabilityMessage) }
    var baseUrl by remember { mutableStateOf(initialBaseUrl) }
    var code by remember { mutableStateOf("") }
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
            Text("Conecta Health Connect con tu servidor HealthIA mediante una dirección local y un código temporal.")

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
                    Text("Ejemplo: http://192.168.1.25:8000 · no uses 127.0.0.1 en el teléfono")
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
