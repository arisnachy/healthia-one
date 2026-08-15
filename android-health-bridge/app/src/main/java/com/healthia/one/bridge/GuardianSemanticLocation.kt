package com.healthia.one.bridge

import android.Manifest
import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import java.time.Instant

/**
 * Device-local semantic place context for HealthIA Guardian.
 *
 * Raw coordinates are used only on this Android device to register geofences.
 * HealthIA sync receives only a coarse label (home/work/gym/unknown) plus an
 * explicit authorization flag. There is intentionally no API here that returns
 * latitude/longitude to the backend payload.
 */
object GuardianSemanticLocation {
    private const val PREFS = "healthia_guardian_location"
    private const val ENABLED = "enabled"
    private const val CURRENT_LABEL = "current_label"
    private const val CURRENT_AT = "current_at"
    private const val PREFIX = "place_"
    private const val DEFAULT_RADIUS_METERS = 180f

    val supportedLabels: Set<String> = setOf("home", "work", "gym")

    fun enabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(ENABLED, false)

    fun hasForegroundPermission(context: Context): Boolean =
        context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun hasBackgroundPermission(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            context.checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun currentLabel(context: Context): String {
        if (!enabled(context)) return "unknown"
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(CURRENT_LABEL, "unknown")
            .orEmpty()
            .lowercase()
            .takeIf { it in supportedLabels }
            ?: "unknown"
    }

    fun metadata(context: Context): Map<String, Any> {
        val active = enabled(context)
        return mapOf(
            "semantic_location_authorized" to active,
            "location_context" to if (active) currentLabel(context) else "unknown",
            "semantic_location_source" to "android_local_geofence",
        )
    }

    fun enrich(context: Context, records: List<HealthRecordDto>): List<HealthRecordDto> {
        if (!enabled(context)) return records
        val locationMetadata = metadata(context)
        return records.map { record ->
            record.copy(metadata = record.metadata + locationMetadata)
        }
    }

    fun savedLabels(context: Context): Set<String> = supportedLabels.filterTo(linkedSetOf()) { label ->
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).contains("${PREFIX}${label}_lat") &&
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).contains("${PREFIX}${label}_lng")
    }

    @SuppressLint("MissingPermission")
    fun captureCurrentPlace(
        context: Context,
        label: String,
        callback: (Boolean, String) -> Unit,
    ) {
        val normalized = label.trim().lowercase()
        if (normalized !in supportedLabels) {
            callback(false, "Unsupported Guardian place label")
            return
        }
        if (!hasForegroundPermission(context)) {
            callback(false, "Foreground location permission is required before saving a Guardian place.")
            return
        }

        val client = LocationServices.getFusedLocationProviderClient(context)
        val token = CancellationTokenSource()
        client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, token.token)
            .addOnSuccessListener { location ->
                if (location == null) {
                    callback(false, "Android could not obtain a current location. Try again with Location enabled.")
                    return@addOnSuccessListener
                }
                val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                prefs.edit()
                    .putBoolean(ENABLED, true)
                    .putLong("${PREFIX}${normalized}_lat", java.lang.Double.doubleToRawLongBits(location.latitude))
                    .putLong("${PREFIX}${normalized}_lng", java.lang.Double.doubleToRawLongBits(location.longitude))
                    .putFloat("${PREFIX}${normalized}_radius", DEFAULT_RADIUS_METERS)
                    .putString(CURRENT_LABEL, normalized)
                    .putString(CURRENT_AT, Instant.now().toString())
                    .apply()
                registerSavedGeofences(context) { ok, message ->
                    callback(
                        ok,
                        if (ok) {
                            "Guardian saved $normalized on this phone. Only the semantic label can be attached to HealthIA signals."
                        } else {
                            message
                        },
                    )
                }
            }
            .addOnFailureListener { error ->
                callback(false, "Could not capture Guardian place: ${error.message}")
            }
    }

    @SuppressLint("MissingPermission")
    fun registerSavedGeofences(context: Context, callback: (Boolean, String) -> Unit = { _, _ -> }) {
        if (!enabled(context)) {
            callback(false, "Guardian semantic location is disabled.")
            return
        }
        if (!hasForegroundPermission(context) || !hasBackgroundPermission(context)) {
            callback(false, "Guardian needs foreground and background location permission for geofence updates while the app is away.")
            return
        }
        val geofences = buildGeofences(context)
        if (geofences.isEmpty()) {
            callback(false, "No Guardian places are saved on this phone.")
            return
        }
        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofences(geofences)
            .build()
        LocationServices.getGeofencingClient(context)
            .addGeofences(request, pendingIntent(context))
            .addOnSuccessListener { callback(true, "Guardian semantic geofences are active.") }
            .addOnFailureListener { error -> callback(false, "Could not activate Guardian geofences: ${error.message}") }
    }

    fun disable(context: Context, callback: (Boolean, String) -> Unit = { _, _ -> }) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(ENABLED, false)
            .putString(CURRENT_LABEL, "unknown")
            .remove(CURRENT_AT)
            .apply()
        LocationServices.getGeofencingClient(context)
            .removeGeofences(pendingIntent(context))
            .addOnSuccessListener { callback(true, "Guardian semantic location disabled. Saved place coordinates remain only on this phone until removed.") }
            .addOnFailureListener { callback(true, "Guardian semantic location disabled locally.") }
    }

    fun forgetAllPlaces(context: Context, callback: (Boolean, String) -> Unit = { _, _ -> }) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit().clear().apply()
        LocationServices.getGeofencingClient(context)
            .removeGeofences(pendingIntent(context))
            .addOnCompleteListener {
                callback(true, "Guardian location context and all saved place coordinates were removed from this phone.")
            }
    }

    internal fun setCurrentFromGeofence(context: Context, label: String) {
        if (!enabled(context) || label !in supportedLabels) return
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(CURRENT_LABEL, label)
            .putString(CURRENT_AT, Instant.now().toString())
            .apply()
    }

    internal fun clearCurrentFromGeofence(context: Context, label: String) {
        if (currentLabel(context) != label) return
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(CURRENT_LABEL, "unknown")
            .putString(CURRENT_AT, Instant.now().toString())
            .apply()
    }

    private fun buildGeofences(context: Context): List<Geofence> {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return savedLabels(context).map { label ->
            val latitude = java.lang.Double.longBitsToDouble(prefs.getLong("${PREFIX}${label}_lat", 0L))
            val longitude = java.lang.Double.longBitsToDouble(prefs.getLong("${PREFIX}${label}_lng", 0L))
            val radius = prefs.getFloat("${PREFIX}${label}_radius", DEFAULT_RADIUS_METERS)
            Geofence.Builder()
                .setRequestId("guardian:$label")
                .setCircularRegion(latitude, longitude, radius)
                .setExpirationDuration(Geofence.NEVER_EXPIRE)
                .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER or Geofence.GEOFENCE_TRANSITION_EXIT)
                .build()
        }
    }

    private fun pendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, GuardianGeofenceReceiver::class.java)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0
        return PendingIntent.getBroadcast(context, 43002, intent, flags)
    }
}

class GuardianGeofenceReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.hasError()) return
        val labels = event.triggeringGeofences.orEmpty()
            .mapNotNull { geofence ->
                geofence.requestId.removePrefix("guardian:").takeIf { it in GuardianSemanticLocation.supportedLabels }
            }
        if (labels.isEmpty()) return

        when (event.geofenceTransition) {
            Geofence.GEOFENCE_TRANSITION_ENTER -> {
                GuardianSemanticLocation.setCurrentFromGeofence(context, labels.first())
            }
            Geofence.GEOFENCE_TRANSITION_EXIT -> {
                labels.forEach { GuardianSemanticLocation.clearCurrentFromGeofence(context, it) }
            }
        }
    }
}
