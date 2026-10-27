package fr.julesgourio.kit.ui

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import fr.julesgourio.kit.engine.Engine
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * A sign-in page (OAuth) shown in the app. The redirect to an address starting with `prefix` never loads:
 * it is handed to the Python `finish` action as `url`, then the page closes.
 */
@SuppressLint("SetJavaScriptEnabled")
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WebAuthView(dest: Dest) {
    val nav = LocalNav.current
    val snackbar = LocalSnackbar.current
    val context = LocalContext.current
    val appScope = LocalAppScope.current
    val url = dest.args.optString("url")
    val prefix = dest.args.optString("prefix")
    val finish = dest.args.optString("finish")
    var loading by remember { mutableStateOf(true) }
    var finishing by remember { mutableStateOf(false) }

    fun done(redirect: String) {
        if (finishing) return
        finishing = true
        appScope.launch {
            val r = Engine.action(finish, JSONObject().put("url", redirect))
            nav.pop()
            applyResult(r, nav, context, { m -> appScope.launch { snackbar.showSnackbar(m) } }) {}
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(dest.args.str("title") ?: "Connexion") },
                navigationIcon = { IconButton(onClick = { nav.pop() }) { Icon(Icons.Filled.Close, "Fermer") } },
            )
        },
        contentWindowInsets = WindowInsets(0),
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (finishing) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            } else {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { ctx ->
                        WebView(ctx).apply {
                            settings.javaScriptEnabled = true
                            settings.domStorageEnabled = true
                            webViewClient = object : WebViewClient() {
                                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                    val u = request.url.toString()
                                    if (u.startsWith(prefix)) {
                                        done(u)
                                        return true
                                    }
                                    return false
                                }

                                override fun onPageStarted(view: WebView, u: String?, favicon: Bitmap?) {
                                    loading = true
                                    if (u != null && u.startsWith(prefix)) {
                                        view.stopLoading()
                                        done(u)
                                    }
                                }

                                override fun onPageFinished(view: WebView, u: String?) {
                                    loading = false
                                }

                                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                                    val u = request.url.toString()
                                    if (request.isForMainFrame && u.startsWith(prefix)) done(u)
                                }
                            }
                            loadUrl(url)
                        }
                    },
                )
            }
        }
    }
}
