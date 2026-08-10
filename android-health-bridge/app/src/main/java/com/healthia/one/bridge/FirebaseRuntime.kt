package com.healthia.one.bridge

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

object FirebaseRuntime {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun configured(): Boolean = listOf(
        BuildConfig.FIREBASE_APP_ID,
        BuildConfig.FIREBASE_API_KEY,
        BuildConfig.FIREBASE_PROJECT_ID,
        BuildConfig.FIREBASE_SENDER_ID,
    ).all { it.isNotBlank() }

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
        if (!initialize(context)) return
        FirebaseMessaging.getInstance().token.addOnSuccessListener { registrationToken ->
            if (registrationToken.isBlank()) return@addOnSuccessListener
            uploadRegistration(context, registrationToken)
        }
    }

    fun uploadRegistration(context: Context, registrationToken: String) {
        if (registrationToken.isBlank()) return
        val preferences = context.getSharedPreferences("healthia", Context.MODE_PRIVATE)
        val baseUrl = preferences.getString("base_url", "").orEmpty()
        val accessToken = preferences.getString("access_token", "").orEmpty()
        val deviceId = preferences.getString("device_id", "").orEmpty()
        if (baseUrl.isBlank() || accessToken.isBlank() || deviceId.isBlank()) return
        scope.launch {
            runCatching {
                HealthiaApi.registerFcm(baseUrl, accessToken, deviceId, registrationToken)
            }
            // Deliberately do not log the registration token or server response.
        }
    }

    fun acknowledgeDelivery(context: Context, proofId: String) {
        if (proofId.length !in 8..128 || proofId.any { !(it.isLetterOrDigit() || it in "._:-") }) return
        val preferences = context.getSharedPreferences("healthia", Context.MODE_PRIVATE)
        val baseUrl = preferences.getString("base_url", "").orEmpty()
        val accessToken = preferences.getString("access_token", "").orEmpty()
        val deviceId = preferences.getString("device_id", "").orEmpty()
        if (baseUrl.isBlank() || accessToken.isBlank() || deviceId.isBlank()) return
        scope.launch {
            runCatching {
                HealthiaApi.acknowledgeFcm(baseUrl, accessToken, deviceId, proofId)
            }
            // The proof id is synthetic operational evidence; never log payload data.
        }
    }
}
