plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.mbm.clipops.pocket"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.mbm.clipops.pocket"
        minSdk = 29
        targetSdk = 35
        ndk { abiFilters += listOf("arm64-v8a") }
        versionCode = 2
        versionName = "0.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    val media3Version = "1.11.1"
    implementation("androidx.media3:media3-common:$media3Version")
    implementation("androidx.media3:media3-exoplayer:$media3Version")
    implementation("androidx.media3:media3-ui:$media3Version")
    implementation("androidx.media3:media3-transformer:$media3Version")
    implementation("androidx.media3:media3-effect:$media3Version")
    testImplementation("junit:junit:4.13.2")
}

chaquopy {
    defaultConfig {
        version = "3.11"
        buildPython("python3.11")
    }
}
