package com.healthia.one.bridge

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

object FirebaseRuntime {
    private const val PREFS = "healthia"
    private const val NOTIFICATIONS_ENABLED = "fcm_notifications_enabled"

    fun configured(): Boolean = listOf(
        BuildConfig.FIREBASE_APP_ID,
        BuildConfig.FIREBASE_API_KEY,
        BuildConfig.FIREBASE_PROJECT_ID,
        BuildConfig.FIREBASE_SENDER_ID,
    ).all { it.isNotBlank() }

    fun notificationsEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(NOTIFICATIONS_ENABLED, true)

    fun setNotificationsEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(NOTIFICATIONS_ENABLED, enabled)
            .apply()
        if (!enabled) {
            FcmRegistrationWorker.cancel(context.applicationContext)
        }
    }

    fun initialize(context: Context): Boolean {
        if (!configured()) return false
        if (FirebaseApp.getApps(context).isNotEmpty()) return true
        val options = FirebaseOptions.Builder()
            .setApplicationId(BuildConfig.FIREBASE_APP_ID)
            .setApiKey(BuildConfig.FIREBASE_API_KEY)
            .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
            .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
            .build()
        return FirebaseApp.initializeApp(context, options) != null
    }

    fun syncRegistration(context: Context) {
        if (!notificationsEnabled(context)) return
        if (!initialize(context)) return
        FcmRegistrationWorker.enqueue(context.applicationContext)
    }

    fun acknowledgeDelivery(context: Context, proofId: String) {
        if (!notificationsEnabled(context)) return
        if (proofId.length !in 8..128 || proofId.any { !(it.isLetterOrDigit() || it in "._:-") }) return
        FcmDeliveryAckWorker.enqueue(context.applicationContext, proofId)
    }
}
