package com.healthia.one.bridge

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.UUID
import java.util.concurrent.TimeUnit

class HealthSyncWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result = runCatching {
        val repository = HealthConnectRepository(applicationContext)
        val granted = repository.grantedPermissions()
        if (!granted.containsAll(repository.permissions)) return Result.success()
        val preferences = applicationContext.getSharedPreferences("healthia", Context.MODE_PRIVATE)
        val baseUrl = preferences.getString("base_url", BuildConfig.HEALTHIA_BASE_URL).orEmpty()
        val token = preferences.getString("access_token", "").orEmpty()
        if (baseUrl.isBlank() || token.isBlank()) return Result.success()
        val records = repository.readSince()
        HealthiaApi.sync(baseUrl, token, deviceId(), records, background = true)
        Result.success()
    }.getOrElse { Result.retry() }

    private fun deviceId(): String {
        val preferences = applicationContext.getSharedPreferences("healthia", Context.MODE_PRIVATE)
        return preferences.getString("device_id", null) ?: UUID.randomUUID().toString().also {
            preferences.edit().putString("device_id", it).apply()
        }
    }

    companion object {
        fun schedule(context: Context) {
            val work = PeriodicWorkRequestBuilder<HealthSyncWorker>(15, TimeUnit.MINUTES).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "healthia-health-connect-sync",
                ExistingPeriodicWorkPolicy.UPDATE,
                work,
            )
        }
    }
}
