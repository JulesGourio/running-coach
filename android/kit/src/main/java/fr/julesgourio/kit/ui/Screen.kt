package fr.julesgourio.kit.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import fr.julesgourio.kit.engine.Engine
import fr.julesgourio.kit.engine.Files
import fr.julesgourio.kit.engine.Reply
import fr.julesgourio.kit.work.Scheduler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** What blocks can ask of the screen that shows them. */
class BlockHost(
    val open: (JSONObject) -> Unit,
    val mergeArgs: (JSONObject) -> Unit,
    val run: (name: String, args: JSONObject, confirm: String?) -> Unit,
    val pickFile: (action: String, args: JSONObject, mime: String, confirm: String?) -> Unit,
    val export: (action: String, filename: String) -> Unit,
    val busy: Boolean,
)

private class Pending(val name: String, val args: JSONObject, val confirm: String, val file: Boolean = false, val mime: String = "*/*")

/** Apply an action's result (`appkit.Result`): message, open, back, web sign-in, sync, reload. */
fun applyResult(reply: Reply, nav: KitNav, context: android.content.Context, message: (String) -> Unit, reload: () -> Unit) {
    when (reply) {
        is Reply.Err -> message(reply.message)
        is Reply.Ok -> {
            val r = reply.data as? JSONObject ?: JSONObject()
            r.str("message")?.let { message(it) }
            if (r.bool("sync")) Scheduler.syncNow(context)
            val web = r.obj("webauth")
            val open = r.obj("open")
            when {
                web != null -> nav.push(Dest(WEBAUTH, web))
                r.bool("back") -> nav.pop()
                open != null -> nav.push(Dest(open.optString("screen"), open.obj("args") ?: JSONObject()))
                !r.has("reload") || r.bool("reload") -> reload()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenView(dest: Dest, showBack: Boolean) {
    val nav = LocalNav.current
    val refresh = LocalRefresh.current
    val snackbar = LocalSnackbar.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var page by remember(dest.key) { mutableStateOf(dest.cached) }
    var error by remember(dest.key) { mutableStateOf<String?>(null) }
    var loading by remember(dest.key) { mutableStateOf(false) }
    var busy by remember(dest.key) { mutableStateOf(false) }
    var reloads by remember(dest.key) { mutableIntStateOf(0) }
    var pending by remember(dest.key) { mutableStateOf<Pending?>(null) }
    var picking by remember(dest.key) { mutableStateOf<Pending?>(null) }
    var exporting by remember(dest.key) { mutableStateOf<Pair<String, String>?>(null) }

    LaunchedEffect(dest.key, refresh, reloads) {
        loading = true
        when (val r = Engine.screen(dest.screen, dest.args)) {
            is Reply.Ok -> {
                val p = r.data as? JSONObject
                if (p != null) {
                    page = p
                    dest.cached = p
                    error = null
                } else error = "réponse inattendue"
            }
            is Reply.Err -> error = r.message
        }
        loading = false
    }

    val appScope = LocalAppScope.current
    val say: (String) -> Unit = { m -> appScope.launch { snackbar.showSnackbar(m) } }
    fun runNow(name: String, args: JSONObject) {
        if (busy) return
        busy = true
        scope.launch {
            val r = Engine.action(name, args)
            busy = false
            applyResult(r, nav, context, say) { reloads++ }
        }
    }

    val openDoc = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        val p = picking
        picking = null
        if (uri != null && p != null) {
            scope.launch {
                busy = true
                val file = withContext(Dispatchers.IO) { runCatching { Files.toCache(context, uri) } }
                busy = false
                file.onSuccess { f ->
                    runNow(p.name, p.args.merged(JSONObject().put("path", f.absolutePath).put("name", f.name)))
                }.onFailure { say(it.message ?: "fichier illisible") }
            }
        }
    }
    val createDoc = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri: Uri? ->
        val e = exporting
        exporting = null
        if (uri != null && e != null) exportTo(scope, context, e.first, e.second, uri, say) { busy = it }
    }

    val host = BlockHost(
        open = { link -> nav.push(Dest(link.optString("screen"), link.obj("args") ?: JSONObject())) },
        mergeArgs = { extra -> nav.replaceTop(Dest(dest.screen, dest.args.merged(extra)).also { it.cached = page }) },
        run = { name, args, confirm -> if (confirm != null) pending = Pending(name, args, confirm) else runNow(name, args) },
        pickFile = { name, args, mime, confirm ->
            val p = Pending(name, args, confirm ?: "", file = true, mime = mime)
            if (confirm != null) pending = p else {
                picking = p
                openDoc.launch(arrayOf(mime))
            }
        },
        export = { name, filename ->
            exporting = name to filename
            createDoc.launch(filename)
        },
        busy = busy,
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(page?.str("title") ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis)
                        page?.str("subtitle")?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                },
                navigationIcon = {
                    if (showBack) IconButton(onClick = { nav.pop() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Retour") }
                },
            )
        },
        contentWindowInsets = WindowInsets(0),
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = loading && page != null,
            onRefresh = { reloads++ },
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            val p = page
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                when {
                    p == null && error == null -> item { Spinner() }
                    p == null -> item { ErrorBox(error ?: "", retry = { reloads++ }) }
                    else -> {
                        error?.let { e -> item { ErrorBox(e, retry = { reloads++ }) } }
                        items(p.list("blocks")) { b -> Block(b, host) }
                    }
                }
                item { Spacer(Modifier.height(24.dp)) }
            }
            if (busy) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        }
    }

    pending?.let { p ->
        AlertDialog(
            onDismissRequest = { pending = null },
            title = { Text("Confirmer") },
            text = { Text(p.confirm) },
            confirmButton = {
                Button(onClick = {
                    pending = null
                    if (p.file) {
                        picking = p
                        openDoc.launch(arrayOf(p.mime))
                    } else runNow(p.name, p.args)
                }) { Text("Confirmer") }
            },
            dismissButton = { TextButton(onClick = { pending = null }) { Text("Annuler") } },
        )
    }
}

private fun exportTo(
    scope: CoroutineScope, context: android.content.Context, action: String, filename: String, uri: Uri,
    say: (String) -> Unit, setBusy: (Boolean) -> Unit,
) {
    scope.launch {
        setBusy(true)
        val tmp = Files.exportFile(context, filename)
        val r = Engine.action(action, JSONObject().put("dest", tmp.absolutePath))
        val copied = if (r is Reply.Ok) withContext(Dispatchers.IO) { runCatching { Files.copyToUri(context, tmp, uri) } } else null
        tmp.delete()
        setBusy(false)
        when {
            r is Reply.Err -> say(r.message)
            copied?.isFailure == true -> say(copied.exceptionOrNull()?.message ?: "écriture impossible")
            else -> say((r as Reply.Ok).let { (it.data as? JSONObject)?.str("message") } ?: "Fichier enregistré.")
        }
    }
}

@Composable
fun Spinner() {
    Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable
fun ErrorBox(message: String, retry: (() -> Unit)? = null) {
    Column(
        Modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Données indisponibles", style = MaterialTheme.typography.titleMedium)
        Text(message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
        if (retry != null) Button(onClick = retry) { Text("Réessayer") }
    }
}
