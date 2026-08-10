package com.healthia.one.bridge

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

class FcmDeliveryAckWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val proofId = inputData.getString(KEY_PROOF_ID).orEmpty()
        val notificationShown = inputData.getBoolean(KEY_NOTIFICATION_SHOWN, false)
        if (!validProofId(proofId)) return Result.failure()

        val preferences = applicationContext.getSharedPreferences("healthia", Context.MODE_PRIVATE)
        val baseUrl = preferences.getString("base_url", "").orEmpty()
        val accessToken = preferences.getString("access_token", "").orEmpty()
        val deviceId = preferences.getString("device_id", "").orEmpty()
        if (baseUrl.isBlank() || accessToken.isBlank() || deviceId.isBlank()) return retryOrFail()

        return runCatching {
            HealthiaApi.acknowledgeFcm(baseUrl, accessToken, deviceId, proofId, notificationShown)
            Result.success()
        }.getOrElse {
            retryOrFail()
        }
    }

    private fun retryOrFail(): Result =
        if (runAttemptCount >= MAX_RETRY_ATTEMPTS) Result.failure() else Result.retry()

    companion object {
        private const val KEY_PROOF_ID = "proof_id"
        private const val KEY_NOTIFICATION_SHOWN = "notification_shown"
        private const val MAX_RETRY_ATTEMPTS = 5

        fun enqueue(context: Context, proofId: String, notificationShown: Boolean) {
            if (!validProofId(proofId)) return
            val request = OneTimeWorkRequestBuilder<FcmDeliveryAckWorker>()
                .setInputData(
                    workDataOf(
                        KEY_PROOF_ID to proofId,
                        KEY_NOTIFICATION_SHOWN to notificationShown,
                    )
                )
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()
            WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
                "healthia-fcm-ack-${proofHash(proofId)}",
                ExistingWorkPolicy.KEEP,
                request,
            )
        }

        private fun validProofId(value: String): Boolean =
            value.length in 8..128 && value.all { it.isLetterOrDigit() || it in "._:-" }

        private fun proofHash(value: String): String =
            MessageDigest.getInstance("SHA-256")
                .digest(value.toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it) }
                .take(24)
    }
}
