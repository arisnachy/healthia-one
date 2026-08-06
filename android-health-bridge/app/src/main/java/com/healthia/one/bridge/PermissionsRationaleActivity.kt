package com.healthia.one.bridge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class PermissionsRationaleActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                PermissionRationale(onClose = ::finish)
            }
        }
    }
}

@Composable
private fun PermissionRationale(onClose: () -> Unit) {
    Surface(Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("Cómo usa HealthIA tus datos", style = MaterialTheme.typography.headlineSmall)
            Text(
                "HealthIA Bridge solo lee los tipos de Health Connect que tú autorizas y los envía " +
                    "al servidor HealthIA que indicaste. Cada registro conserva fecha, procedencia y dispositivo."
            )
            Text(
                "HealthIA no vende estos datos, no modifica tratamientos y no convierte una medición " +
                    "aislada en un diagnóstico. Puedes revocar los permisos desde Health Connect cuando quieras."
            )
            Button(onClick = onClose) { Text("Entendido") }
        }
    }
}
