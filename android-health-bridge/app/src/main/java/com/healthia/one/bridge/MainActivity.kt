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
        setContent {
            MaterialTheme {
                BridgeScreen(repository.permissions) { syncNow() }
            }
        }
    }

    private fun syncNow() {
        lifecycleScope.launch {
            runCatching {
                val records = repository.readSince()
                withContext(Dispatchers.IO) {
                    HealthiaApi.sync(BuildConfig.HEALTHIA_BASE_URL, deviceId(), records, background = false)
                }
                HealthSyncWorker.schedule(this@MainActivity)
            }
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
private fun BridgeScreen(permissions: Set<String>, syncNow: () -> Unit) {
    var status by remember { mutableStateOf("Not connected") }
    val permissionLauncher = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status = if (granted.containsAll(permissions)) "Connected" else "Some permissions were not granted"
    }
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("HealthIA Android Bridge", style = MaterialTheme.typography.headlineSmall)
            Text("Health Connect shares only the data types the patient authorizes.")
            Text(status)
            Button(onClick = { permissionLauncher.launch(permissions) }) { Text("Connect Health Connect") }
            OutlinedButton(onClick = syncNow) { Text("Sync now") }
            Text("Background synchronization uses WorkManager and is not a guaranteed clinical real-time stream.")
        }
    }
}
