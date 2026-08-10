package com.healthia.one.bridge

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.Instant

object HealthiaApi {
    fun claim(baseUrl: String, code: String, deviceId: String, displayName: String): String {
        val payload = JSONObject().apply {
            put("code", code)
            put("device_id", deviceId)
            put("display_name", displayName)
        }
        val body = request(baseUrl, "/api/devices/pairing/claim", payload, token = null)
        return JSONObject(body).getString("access_token")
    }

    fun sync(baseUrl: String, token: String, deviceId: String, records: List<HealthRecordDto>, background: Boolean, grantedMetrics: List<String>): String {
        val payload = JSONObject().apply {
            put("device_id", deviceId)
            put("source_package", "com.healthia.one.bridge")
            put("synced_at", Instant.now().toString())
            put("background_read", background)
            put("granted_metrics", JSONArray(grantedMetrics))
            put("records", JSONArray().apply {
                records.forEach { record ->
                    put(JSONObject().apply {
                        put("external_id", record.externalId)
                        put("metric", record.metric)
                        put("observed_at", record.observedAt)
                        put("value", record.value)
                        if (record.secondaryValue != null) put("secondary_value", record.secondaryValue)
                        put("unit", record.unit)
                        put("source_package", record.sourcePackage)
                        put("source_name", record.sourceName)
                        put("device_manufacturer", record.manufacturer)
                        put("device_model", record.model)
                        put("device_type", record.deviceType)
                        put("recording_method", record.recordingMethod)
                    })
                }
            })
        }
        return request(baseUrl, "/api/devices/health-connect/sync", payload, token)
    }

    fun registerFcm(baseUrl: String, token: String, deviceId: String, registrationToken: String): String {
        val payload = JSONObject().apply {
            put("device_id", deviceId)
            put("registration_token", registrationToken)
        }
        return request(baseUrl, "/api/devices/fcm/register", payload, token)
    }

    fun explicitlyEnableFcm(baseUrl: String, token: String, deviceId: String, registrationToken: String): String {
        val payload = JSONObject().apply {
            put("device_id", deviceId)
            put("registration_token", registrationToken)
            put("notifications_opt_in", true)
        }
        return request(baseUrl, "/api/devices/fcm/register/enable", payload, token)
    }

    fun disableFcm(baseUrl: String, token: String, deviceId: String): String {
        val encodedDeviceId = URLEncoder.encode(deviceId, StandardCharsets.UTF_8)
        return request(
            baseUrl,
            "/api/devices/fcm/register/$encodedDeviceId",
            payload = null,
            token = token,
            method = "DELETE",
        )
    }

    fun acknowledgeFcm(baseUrl: String, token: String, deviceId: String, proofId: String): String {
        val payload = JSONObject().apply {
            put("device_id", deviceId)
            put("proof_id", proofId)
        }
        return request(baseUrl, "/api/devices/fcm/ack", payload, token)
    }

    private fun request(
        baseUrl: String,
        path: String,
        payload: JSONObject?,
        token: String?,
        method: String = "POST",
    ): String {
        val connection = (URL("${baseUrl.trimEnd('/')}$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15_000
            readTimeout = 30_000
            doOutput = payload != null
            setRequestProperty("Accept", "application/json")
            if (payload != null) setRequestProperty("Content-Type", "application/json")
            if (!token.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $token")
        }
        if (payload != null) {
            connection.outputStream.use { it.write(payload.toString().toByteArray()) }
        }
        val responseCode = connection.responseCode
        val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (responseCode !in 200..299) error("HealthIA request failed: $responseCode $body")
        return body
    }
}
