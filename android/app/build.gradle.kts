import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.chaquopy)
}

// The shared Android kit (android/kit): Kotlin shell + `appkit` Python package, compiled into this app.
val kit = rootProject.file("kit")

android {
    namespace = "fr.julesgourio.coach"
    compileSdk = 36

    defaultConfig {
        applicationId = "fr.julesgourio.coach"
        minSdk = 26
        targetSdk = 36
        // CI sets the run number so every APK installs over the previous one.
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "0.1." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
        ndk {
            // The Pixel 8a and every recent phone.
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        // One fixed key for every build (CI and PC), so a new APK updates the app instead of requiring an
        // uninstall that would erase its data. Sideloaded app, not published.
        create("coach") {
            storeFile = file("coach.keystore")
            storePassword = "carnetdecourse"
            keyAlias = "coach"
            keyPassword = "carnetdecourse"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("coach")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("coach")
        }
    }

    sourceSets {
        getByName("main") {
            java.srcDir(kit.resolve("src/main/java"))
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

// The Python engine is the repository's own `coach` package, copied at build time (never duplicated in git).
// PC-only modules stay out: the MCP server, the HTTP API, the CLI and the `mcp`-based COROS client.
val copyEngine by tasks.registering(Sync::class) {
    from(rootProject.file("../coach")) {
        exclude("**/__pycache__/**", "mcp_server.py", "api.py", "cli.py", "sources/coros_mcp.py")
    }
    into(layout.buildDirectory.dir("python-src/coach"))
}
tasks.named("preBuild") { dependsOn(copyEngine) }

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            install("-r", "requirements.txt")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir(layout.buildDirectory.dir("python-src"))
            srcDir(kit.resolve("python"))
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.fragment.ktx)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.biometric)
    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
}
