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
import com.google.android.gms.tasks.Tasks
import com.google.firebase.messaging.FirebaseMessaging
import java.util.concurrent.TimeUnit

class FcmRegistrationWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        if (!FirebaseRuntime.initialize(applicationContext)) return Result.success()

        val preferences = applicationContext.getSharedPreferences("healthia", Context.MODE_PRIVATE)
        val baseUrl = preferences.getString("base_url", "").orEmpty()
        val accessToken = preferences.getString("access_token", "").orEmpty()
        val deviceId = preferences.getString("device_id", "").orEmpty()
        if (baseUrl.isBlank() || accessToken.isBlank() || deviceId.isBlank()) return Result.success()

        return runCatching {
            val registrationToken = Tasks.await(
                FirebaseMessaging.getInstance().token,
                TOKEN_TIMEOUT_SECONDS,
                TimeUnit.SECONDS,
            ).orEmpty()
            if (registrationToken.isBlank()) return@runCatching retryOrFail()
            HealthiaApi.registerFcm(baseUrl, accessToken, deviceId, registrationToken)
            Result.success()
        }.getOrElse {
            retryOrFail()
        }
    }

    private fun retryOrFail(): Result =
        if (runAttemptCount >= MAX_RETRY_ATTEMPTS) Result.failure() else Result.retry()

    companion object {
        private const val UNIQUE_WORK = "healthia-fcm-registration"
        private const val TOKEN_TIMEOUT_SECONDS = 20L
        private const val MAX_RETRY_ATTEMPTS = 5

        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<FcmRegistrationWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()
            WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
                UNIQUE_WORK,
                ExistingWorkPolicy.REPLACE,
                request,
            )
        }
    }
}
