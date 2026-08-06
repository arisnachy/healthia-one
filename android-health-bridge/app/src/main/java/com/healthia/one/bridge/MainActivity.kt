package com.healthia.one.bridge

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
                    initialBaseUrl = preferences.getString("base_url", BuildConfig.HEALTHIA_BASE_URL).orEmpty(),
                    connect = { baseUrl, code, updateStatus -> connectBridge(baseUrl, code, updateStatus) },
                    syncNow = { updateStatus -> syncNow(updateStatus) },
                )
            }
        }
    }

    private fun connectBridge(baseUrl: String, code: String, updateStatus: (String) -> Unit) {
        lifecycleScope.launch {
            updateStatus("Connecting…")
            runCatching {
                val token = withContext(Dispatchers.IO) {
                    HealthiaApi.claim(baseUrl, code, deviceId(), "HealthIA Android Bridge")
                }
                getSharedPreferences("healthia", MODE_PRIVATE).edit()
                    .putString("base_url", baseUrl.trimEnd('/'))
                    .putString("access_token", token)
                    .apply()
                updateStatus("Paired. Grant Health Connect permissions, then sync.")
            }.onFailure { updateStatus("Pairing failed: ${it.message}") }
        }
    }

    private fun syncNow(updateStatus: (String) -> Unit) {
        lifecycleScope.launch {
            updateStatus("Syncing…")
            runCatching {
                val preferences = getSharedPreferences("healthia", MODE_PRIVATE)
                val baseUrl = preferences.getString("base_url", "").orEmpty()
                val token = preferences.getString("access_token", "").orEmpty()
                require(baseUrl.isNotBlank() && token.isNotBlank()) { "Pair the bridge first" }
                val records = repository.readSince()
                withContext(Dispatchers.IO) {
                    HealthiaApi.sync(baseUrl, token, deviceId(), records, background = false)
                }
                HealthSyncWorker.schedule(this@MainActivity)
                updateStatus("Synced ${records.size} records")
            }.onFailure { updateStatus("Sync failed: ${it.message}") }
        }
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
    initialBaseUrl: String,
    connect: (String, String, (String) -> Unit) -> Unit,
    syncNow: ((String) -> Unit) -> Unit,
) {
    var status by remember { mutableStateOf("Not paired") }
    var baseUrl by remember { mutableStateOf(initialBaseUrl) }
    var code by remember { mutableStateOf("") }
    val permissionLauncher = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status = if (granted.containsAll(permissions)) "Health Connect permissions granted" else "Some permissions were not granted"
    }
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("HealthIA Android Bridge", style = MaterialTheme.typography.headlineSmall)
            Text("Enter the backend address and the six-digit code shown in HealthIA ONE.")
            OutlinedTextField(baseUrl, { baseUrl = it }, label = { Text("Backend URL") }, singleLine = true)
            OutlinedTextField(code, { code = it.filter(Char::isDigit).take(6) }, label = { Text("Pairing code") }, singleLine = true)
            Text(status)
            Button(
                enabled = baseUrl.isNotBlank() && code.length == 6,
                onClick = { connect(baseUrl, code) { status = it } },
            ) { Text("Pair with HealthIA") }
            OutlinedButton(onClick = { permissionLauncher.launch(permissions) }) { Text("Grant Health Connect permissions") }
            OutlinedButton(onClick = { syncNow { status = it } }) { Text("Sync now") }
            Text("Background synchronization uses WorkManager and is not a guaranteed clinical real-time stream.")
        }
    }
}
