package com.healthia.one.bridge

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class HealthiaFirebaseMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        if (token.isBlank() || !FirebaseRuntime.notificationsEnabled(applicationContext)) return
        FirebaseRuntime.syncRegistration(applicationContext)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        if (!FirebaseRuntime.notificationsEnabled(applicationContext)) return
        val proofId = message.data["proof_id"].orEmpty()
        val kind = message.data["kind"].orEmpty()
        if (kind != "healthia_update" || !validProofId(proofId)) return

        val notificationShown = showNeutralNotification()
        FirebaseRuntime.acknowledgeDelivery(applicationContext, proofId, notificationShown)
    }

    private fun validProofId(value: String): Boolean =
        value.length in 8..128 && value.all { it.isLetterOrDigit() || it in "._:-" }

    private fun showNeutralNotification(): Boolean {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }

        val channelId = "healthia_updates"
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                channelId,
                "HealthIA updates",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Private HealthIA update notifications"
            }
        )

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("HealthIA")
            .setContentText("Tienes una actualización disponible en HealthIA.")
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()

        manager.notify(42001, notification)
        return true
    }
}
