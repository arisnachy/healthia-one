plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val firebaseAppId = providers.gradleProperty("HEALTHIA_FIREBASE_APP_ID")
    .orElse(providers.environmentVariable("HEALTHIA_FIREBASE_APP_ID"))
    .orElse("")
    .get()
val firebaseApiKey = providers.gradleProperty("HEALTHIA_FIREBASE_API_KEY")
    .orElse(providers.environmentVariable("HEALTHIA_FIREBASE_API_KEY"))
    .orElse("")
    .get()
val firebaseProjectId = providers.gradleProperty("HEALTHIA_FIREBASE_PROJECT_ID")
    .orElse(providers.environmentVariable("HEALTHIA_FIREBASE_PROJECT_ID"))
    .orElse("")
    .get()
val firebaseSenderId = providers.gradleProperty("HEALTHIA_FIREBASE_SENDER_ID")
    .orElse(providers.environmentVariable("HEALTHIA_FIREBASE_SENDER_ID"))
    .orElse("")
    .get()

fun quotedBuildValue(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

android {
    namespace = "com.healthia.one.bridge"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.healthia.one.bridge"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "HEALTHIA_BASE_URL", "\"http://10.0.2.2:8000\"")
        // Firebase identifiers/config are injected by the build environment and
        // never committed as google-services.json or runtime secrets.
        buildConfigField("String", "FIREBASE_APP_ID", quotedBuildValue(firebaseAppId))
        buildConfigField("String", "FIREBASE_API_KEY", quotedBuildValue(firebaseApiKey))
        buildConfigField("String", "FIREBASE_PROJECT_ID", quotedBuildValue(firebaseProjectId))
        buildConfigField("String", "FIREBASE_SENDER_ID", quotedBuildValue(firebaseSenderId))
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.material3:material3:1.3.2")
    implementation("androidx.compose.ui:ui:1.7.8")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.work:work-runtime-ktx:2.10.1")
    implementation("androidx.health.connect:connect-client:1.1.0")
    implementation("com.google.android.gms:play-services-location:21.4.0")
    implementation(platform("com.google.firebase:firebase-bom:34.16.0"))
    implementation("com.google.firebase:firebase-messaging")
}
