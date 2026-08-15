package com.healthia.one.bridge

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.permission.HealthPermission.Companion.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
import androidx.health.connect.client.records.*
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import java.time.Duration
import java.time.Instant
import java.time.temporal.ChronoUnit

class HealthConnectRepository(private val context: Context) {
    private val providerPackageName = "com.google.android.apps.healthdata"
    private val sdkStatus = HealthConnectClient.getSdkStatus(context, providerPackageName)

    val isAvailable: Boolean = sdkStatus == HealthConnectClient.SDK_AVAILABLE
    val providerUpdateRequired: Boolean =
        sdkStatus == HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED

    private val client: HealthConnectClient by lazy {
        check(isAvailable) { availabilityMessage() }
        HealthConnectClient.getOrCreate(context, providerPackageName)
    }

    val supportsBackgroundRead: Boolean
        get() = isAvailable && client.features.getFeatureStatus(
            HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND
        ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE

    private val metricPermissions: Map<String, String>
        get() = linkedMapOf(
            "steps" to HealthPermission.getReadPermission(StepsRecord::class),
            "heart_rate" to HealthPermission.getReadPermission(HeartRateRecord::class),
            "blood_pressure" to HealthPermission.getReadPermission(BloodPressureRecord::class),
            "weight" to HealthPermission.getReadPermission(WeightRecord::class),
            "height" to HealthPermission.getReadPermission(HeightRecord::class),
            "oxygen_saturation" to HealthPermission.getReadPermission(OxygenSaturationRecord::class),
            "respiratory_rate" to HealthPermission.getReadPermission(RespiratoryRateRecord::class),
            "body_temperature" to HealthPermission.getReadPermission(BodyTemperatureRecord::class),
            "blood_glucose" to HealthPermission.getReadPermission(BloodGlucoseRecord::class),
            "menstruation_period" to HealthPermission.getReadPermission(MenstruationPeriodRecord::class),
        )

    // These records are context for an authorized signal, not standalone
    // HealthIA clinical measurements. They are requested explicitly from Health
    // Connect and only used when the user granted their record permission.
    private val contextPermissions: Map<String, String>
        get() = linkedMapOf(
            "exercise_session" to HealthPermission.getReadPermission(ExerciseSessionRecord::class),
            "hrv_rmssd" to HealthPermission.getReadPermission(HeartRateVariabilityRmssdRecord::class),
            "sleep_session" to HealthPermission.getReadPermission(SleepSessionRecord::class),
        )

    val dataPermissions: Set<String>
        get() = metricPermissions.values.toSet()

    val permissions: Set<String>
        get() = buildSet {
            addAll(dataPermissions)
            addAll(contextPermissions.values)
            if (supportsBackgroundRead) add(PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND)
        }

    fun availabilityMessage(): String = when {
        isAvailable -> "Health Connect está disponible"
        providerUpdateRequired -> "Health Connect debe instalarse o actualizarse"
        else -> "Health Connect no está disponible en este teléfono"
    }

    fun providerInstallIntent(): Intent = Intent(Intent.ACTION_VIEW).apply {
        setPackage("com.android.vending")
        data = Uri.parse(
            "market://details?id=$providerPackageName&url=healthconnect%3A%2F%2Fonboarding"
        )
        putExtra("overlay", true)
        putExtra("callerId", context.packageName)
    }

    fun manageDataIntent(): Intent =
        HealthConnectClient.getHealthConnectManageDataIntent(context, providerPackageName)

    suspend fun grantedPermissions(): Set<String> {
        requireAvailable()
        return client.permissionController.getGrantedPermissions()
    }

    suspend fun grantedMetricNames(): List<String> {
        val granted = grantedPermissions()
        return metricPermissions.filterValues { it in granted }.keys.toList()
    }

    suspend fun grantedContextNames(): List<String> {
        val granted = grantedPermissions()
        return contextPermissions.filterValues { it in granted }.keys.toList()
    }

    suspend fun readSince(start: Instant = Instant.now().minus(24, ChronoUnit.HOURS)): List<HealthRecordDto> {
        requireAvailable()
        val granted = grantedPermissions()
        require(metricPermissions.values.any { it in granted }) {
            "Concede al menos un tipo de dato en Health Connect"
        }

        val end = Instant.now()
        val range = TimeRangeFilter.between(start, end)
        val output = mutableListOf<HealthRecordDto>()

        val exerciseSessions = if (contextPermissions.getValue("exercise_session") in granted) {
            read<ExerciseSessionRecord>(range)
        } else {
            emptyList()
        }
        val hrvRecords = if (contextPermissions.getValue("hrv_rmssd") in granted) {
            read<HeartRateVariabilityRmssdRecord>(range)
        } else {
            emptyList()
        }
        val sleepSessions = if (contextPermissions.getValue("sleep_session") in granted) {
            read<SleepSessionRecord>(range)
        } else {
            emptyList()
        }

        fun contextAt(time: Instant): Map<String, Any> {
            val metadata = linkedMapOf<String, Any>()
            val exercise = exerciseSessions
                .filter { !time.isBefore(it.startTime) && !time.isAfter(it.endTime) }
                .maxByOrNull { it.startTime }
            if (exercise != null) {
                metadata["exercise_session_active"] = true
                metadata["activity_type"] = exerciseTypeLabel(exercise.exerciseType)
                metadata["exercise_type_code"] = exercise.exerciseType
                metadata["exercise_started_at"] = exercise.startTime.toString()
                metadata["exercise_ended_at"] = exercise.endTime.toString()
            }

            val latestHrv = hrvRecords
                .filter { !it.time.isAfter(time) }
                .filter { Duration.between(it.time, time).toMinutes() in 0..360 }
                .maxByOrNull { it.time }
            if (latestHrv != null) {
                metadata["hrv_rmssd_ms"] = latestHrv.heartRateVariabilityMillis
                metadata["hrv_observed_at"] = latestHrv.time.toString()
            }

            val recentSleep = sleepSessions
                .filter { !it.endTime.isAfter(time) }
                .filter { Duration.between(it.endTime, time).toHours() in 0..24 }
                .maxByOrNull { it.endTime }
            if (recentSleep != null) {
                metadata["sleep_minutes"] = Duration.between(recentSleep.startTime, recentSleep.endTime).toMinutes()
                metadata["sleep_ended_at"] = recentSleep.endTime.toString()
            }
            return metadata
        }

        if (metricPermissions.getValue("steps") in granted) read<StepsRecord>(range).forEach { record ->
            output += record.dto("steps", record.count.toDouble(), "count", record.startTime)
        }
        if (metricPermissions.getValue("heart_rate") in granted) read<HeartRateRecord>(range).forEach { record ->
            record.samples.forEachIndexed { index, sample ->
                output += record.dto(
                    "heart_rate",
                    sample.beatsPerMinute.toDouble(),
                    "bpm",
                    sample.time,
                    suffix = index.toString(),
                    guardianMetadata = contextAt(sample.time),
                )
            }
        }
        if (metricPermissions.getValue("blood_pressure") in granted) read<BloodPressureRecord>(range).forEach { record ->
            output += record.dto(
                "blood_pressure",
                record.systolic.inMillimetersOfMercury,
                "mmHg",
                record.time,
                secondary = record.diastolic.inMillimetersOfMercury,
                guardianMetadata = contextAt(record.time),
            )
        }
        if (metricPermissions.getValue("weight") in granted) read<WeightRecord>(range).forEach { record ->
            output += record.dto("weight", record.weight.inKilograms, "kg", record.time)
        }
        if (metricPermissions.getValue("height") in granted) read<HeightRecord>(range).forEach { record ->
            output += record.dto("height", record.height.inMeters * 100.0, "cm", record.time)
        }
        if (metricPermissions.getValue("oxygen_saturation") in granted) read<OxygenSaturationRecord>(range).forEach { record ->
            output += record.dto("oxygen_saturation", record.percentage.value, "%", record.time)
        }
        if (metricPermissions.getValue("respiratory_rate") in granted) read<RespiratoryRateRecord>(range).forEach { record ->
            output += record.dto("respiratory_rate", record.rate, "breaths/min", record.time)
        }
        if (metricPermissions.getValue("body_temperature") in granted) read<BodyTemperatureRecord>(range).forEach { record ->
            output += record.dto("body_temperature", record.temperature.inCelsius, "°C", record.time)
        }
        if (metricPermissions.getValue("blood_glucose") in granted) read<BloodGlucoseRecord>(range).forEach { record ->
            output += record.dto("blood_glucose", record.level.inMilligramsPerDeciliter, "mg/dL", record.time)
        }
        if (metricPermissions.getValue("menstruation_period") in granted) read<MenstruationPeriodRecord>(range).forEach { record ->
            output += record.dto("menstruation_period", 1.0, "period", record.startTime)
        }
        return output
    }

    private fun exerciseTypeLabel(type: Int): String = when (type) {
        ExerciseSessionRecord.EXERCISE_TYPE_RUNNING,
        ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL -> "running"
        ExerciseSessionRecord.EXERCISE_TYPE_WALKING -> "walking"
        ExerciseSessionRecord.EXERCISE_TYPE_BIKING,
        ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY -> "cycling"
        else -> "exercise"
    }

    private fun requireAvailable() {
        check(isAvailable) { availabilityMessage() }
    }

    private suspend inline fun <reified T : Record> read(range: TimeRangeFilter): List<T> =
        client.readRecords(ReadRecordsRequest<T>(timeRangeFilter = range)).records

    private fun Record.dto(
        metric: String,
        value: Double,
        unit: String,
        time: Instant,
        secondary: Double? = null,
        suffix: String = "",
        guardianMetadata: Map<String, Any> = emptyMap(),
    ): HealthRecordDto {
        val metadata = metadata
        val device = metadata.device
        return HealthRecordDto(
            externalId = listOf(metadata.id, suffix).filter { it.isNotBlank() }.joinToString(":"),
            metric = metric,
            observedAt = time.toString(),
            value = value,
            secondaryValue = secondary,
            unit = unit,
            sourcePackage = metadata.dataOrigin.packageName,
            sourceName = metadata.dataOrigin.packageName,
            manufacturer = device?.manufacturer.orEmpty(),
            model = device?.model.orEmpty(),
            deviceType = device?.type?.toString().orEmpty(),
            recordingMethod = metadata.recordingMethod.toString(),
            metadata = guardianMetadata,
        )
    }
}

data class HealthRecordDto(
    val externalId: String,
    val metric: String,
    val observedAt: String,
    val value: Double,
    val secondaryValue: Double?,
    val unit: String,
    val sourcePackage: String,
    val sourceName: String,
    val manufacturer: String,
    val model: String,
    val deviceType: String,
    val recordingMethod: String,
    val metadata: Map<String, Any> = emptyMap(),
)
