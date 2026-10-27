package fr.julesgourio.kit.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.work.WorkInfo
import androidx.work.WorkManager
import fr.julesgourio.kit.Kit
import fr.julesgourio.kit.engine.Engine
import fr.julesgourio.kit.engine.Reply
import fr.julesgourio.kit.work.Scheduler
import fr.julesgourio.kit.work.SyncWorker
import kotlinx.coroutines.launch
import org.json.JSONObject

/** The whole app: lock, tabs from the Python manifest, one back stack per tab. FragmentActivity for the fingerprint prompt. */
open class KitActivity : FragmentActivity() {
    private var unlocked by mutableStateOf(false)
    private var leftAt = 0L
    private var prompting = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (!Kit.config.lock) unlocked = true
        setContent {
            KitTheme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    if (unlocked) KitApp() else Locked(onUnlock = ::unlock)
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!Kit.config.lock) return
        if (unlocked && leftAt > 0 && SystemClock.elapsedRealtime() - leftAt > LOCK_AFTER_MS) unlocked = false
        if (!unlocked && !prompting) unlock()
    }

    override fun onPause() {
        super.onPause()
        leftAt = SystemClock.elapsedRealtime()
    }

    private fun unlock() {
        if (prompting) return
        val allowed = BIOMETRIC_WEAK or DEVICE_CREDENTIAL
        if (BiometricManager.from(this).canAuthenticate(allowed) != BiometricManager.BIOMETRIC_SUCCESS) {
            unlocked = true // no screen lock on the phone: nothing to check against
            return
        }
        val prompt = BiometricPrompt(this, ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    prompting = false
                    unlocked = true
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    prompting = false // cancelled: the lock screen stays, with its button
                }
            })
        prompting = true
        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle(Kit.config.appName)
                .setSubtitle(Kit.config.lockSubtitle)
                .setAllowedAuthenticators(allowed)
                .build(),
        )
    }

    private companion object {
        const val LOCK_AFTER_MS = 5 * 60 * 1000L
    }
}

@Composable
private fun Locked(onUnlock: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.Lock, contentDescription = null)
        Text("${Kit.config.appName} est verrouillé", style = MaterialTheme.typography.titleMedium)
        Button(onClick = onUnlock) { Text("Déverrouiller") }
    }
}

@Composable
private fun KitApp() {
    val context = LocalContext.current
    var manifest by remember { mutableStateOf(Engine.manifest) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }
    LaunchedEffect(attempt) {
        if (manifest == null) {
            error = null
            when (val r = Engine.start()) {
                is Reply.Ok -> manifest = r.data as? JSONObject ?: JSONObject().also { error = "manifeste vide" }
                is Reply.Err -> error = r.message
            }
        }
    }

    // Ask once for the notification permission (Android 13+).
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    val m = manifest
    if (m == null || m.list("tabs").isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            val e = error
            if (e != null) ErrorBox(e, retry = { attempt++ })
            else Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                CircularProgressIndicator()
                Text("Démarrage…", style = MaterialTheme.typography.bodyMedium)
            }
        }
        return
    }
    AppShell(m)
}

@Composable
private fun AppShell(manifest: JSONObject) {
    val context = LocalContext.current
    val tabs = manifest.list("tabs")
    val nav = remember { KitNav(tabs.map { it.optString("screen") }) }
    val snackbar = remember { SnackbarHostState() }
    val appScope = rememberCoroutineScope()

    // Sync: the button's one-off job and the daily one; the screen on show reloads when either finishes.
    val wm = remember { WorkManager.getInstance(context) }
    val now by wm.getWorkInfosForUniqueWorkFlow(Scheduler.NOW).collectAsStateWithLifecycle(emptyList())
    val daily by wm.getWorkInfosForUniqueWorkFlow(Scheduler.DAILY).collectAsStateWithLifecycle(emptyList())
    val running = (now + daily).any { it.state == WorkInfo.State.RUNNING }
    var refresh by remember { mutableIntStateOf(0) }
    var wasRunning by remember { mutableStateOf(false) }
    val lastError = now.firstOrNull { it.state == WorkInfo.State.FAILED }?.outputData?.getString(SyncWorker.KEY_ERROR)
    LaunchedEffect(running) {
        if (wasRunning && !running) {
            refresh++
            lastError?.let { appScope.launch { snackbar.showSnackbar("Synchronisation : $it") } }
        }
        wasRunning = running
    }
    val sync = SyncState(running) { Scheduler.syncNow(context) }

    BackHandler(enabled = nav.stack.size > 1) { nav.pop() }

    CompositionLocalProvider(LocalNav provides nav, LocalRefresh provides refresh, LocalSync provides sync, LocalSnackbar provides snackbar,
        LocalAppScope provides appScope) {
        Scaffold(
            bottomBar = {
                if (tabs.size > 1) NavigationBar {
                    tabs.forEach { t ->
                        val screen = t.optString("screen")
                        NavigationBarItem(
                            selected = nav.tab == screen,
                            onClick = { nav.selectTab(screen) },
                            icon = { Icon(kitIcon(t.str("icon")) ?: Icons.Filled.Circle, contentDescription = null) },
                            label = { Text(t.optString("label"), maxLines = 1) },
                        )
                    }
                }
            },
            snackbarHost = { SnackbarHost(snackbar) },
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(bottom = padding.calculateBottomPadding())) {
                if (running) LinearProgressIndicator(Modifier.fillMaxWidth())
                Box(Modifier.weight(1f)) {
                    val d = nav.current
                    if (d != null) key(d.key) {
                        if (d.screen == WEBAUTH) WebAuthView(d) else ScreenView(d, showBack = nav.stack.size > 1)
                    }
                }
            }
        }
    }
}
