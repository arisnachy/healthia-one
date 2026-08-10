package com.healthia.one.bridge

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

object FirebaseRuntime {
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
        FcmRegistrationWorker.enqueue(context.applicationContext)
    }

    fun acknowledgeDelivery(context: Context, proofId: String) {
        if (proofId.length !in 8..128 || proofId.any { !(it.isLetterOrDigit() || it in "._:-") }) return
        FcmDeliveryAckWorker.enqueue(context.applicationContext, proofId)
    }
}
