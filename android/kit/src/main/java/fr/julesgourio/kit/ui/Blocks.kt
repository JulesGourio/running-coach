package fr.julesgourio.kit.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min

/** Draws one block of `appkit.ui`. Unknown types are skipped, so an older app still opens newer screens. */
@Composable
fun Block(b: JSONObject, host: BlockHost) {
    when (b.optString("t")) {
        "title" -> TitleBlock(b)
        "text" -> TextBlock(b)
        "bullets" -> BulletsBlock(b)
        "alert" -> AlertBlock(b)
        "divider" -> HorizontalDivider()
        "metrics" -> MetricsBlock(b, host)
        "big" -> BigBlock(b)
        "rows" -> RowsBlock(b, host)
        "card" -> CardBlock(b, host)
        "table" -> TableBlock(b)
        "chart" -> Framed { ChartBlock(b) }
        "route" -> Framed { RouteBlock(b) }
        "choice" -> ChoiceBlock(b, host)
        "pager" -> PagerBlock(b, host)
        "button" -> ButtonBlock(b, host)
        "buttons" -> ButtonsBlock(b, host)
        "form" -> FormBlock(b, host)
        "file" -> OutlinedButton(onClick = {
            host.pickFile(b.optString("action"), b.obj("args") ?: JSONObject(), b.optString("mime", "*/*"), b.str("confirm"))
        }, enabled = !host.busy, modifier = Modifier.fillMaxWidth()) { Text(b.optString("label")) }
        "export" -> OutlinedButton(onClick = { host.export(b.optString("action"), b.optString("filename")) },
            enabled = !host.busy, modifier = Modifier.fillMaxWidth()) { Text(b.optString("label")) }
        "sync" -> SyncBlock(b)
        else -> Unit
    }
}

@Composable
private fun muted() = MaterialTheme.colorScheme.onSurfaceVariant

@Composable
private fun Framed(content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Box(Modifier.padding(12.dp)) { content() }
    }
}

@Composable
private fun TitleBlock(b: JSONObject) {
    Column(Modifier.padding(top = 4.dp)) {
        Text(b.optString("text"), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        b.str("sub")?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted()) }
    }
}

@Composable
private fun TextBlock(b: JSONObject) {
    val text = rich(b.optString("text"))
    when (b.optString("style")) {
        "muted" -> Text(text, style = MaterialTheme.typography.bodySmall, color = muted())
        "small" -> Text(text, style = MaterialTheme.typography.labelSmall, color = muted())
        "big" -> Text(text, style = MaterialTheme.typography.headlineSmall)
        else -> Text(text, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun BulletsBlock(b: JSONObject) {
    val style = if (b.optString("style") == "muted") MaterialTheme.typography.bodySmall else MaterialTheme.typography.bodyMedium
    val color = if (b.optString("style") == "muted") muted() else MaterialTheme.colorScheme.onSurface
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        b.strings("items").forEach { item ->
            Row {
                Text("•", Modifier.width(14.dp), style = style, color = color)
                Text(rich(item), style = style, color = color)
            }
        }
    }
}

@Composable
private fun AlertBlock(b: JSONObject) {
    val level = b.optString("level", "info")
    val color = toneColor(level) ?: LocalTones.current.info
    val icon = when (level) {
        "bad" -> Icons.Filled.Error
        "warn" -> Icons.Filled.Warning
        "good" -> Icons.Filled.CheckCircle
        else -> Icons.Filled.Info
    }
    Card(colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.12f).compositeOver(MaterialTheme.colorScheme.surface))) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(icon, null, tint = color)
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(b.optString("title"), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                b.str("text")?.let { Text(rich(it), style = MaterialTheme.typography.bodySmall) }
            }
        }
    }
}

@Composable
private fun MetricsBlock(b: JSONObject, host: BlockHost) {
    val cols = b.optInt("columns", 2).coerceIn(1, 3)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        b.list("items").chunked(cols).forEach { line ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                line.forEach { m ->
                    val link = m.obj("open")
                    Card(
                        Modifier.weight(1f).let { if (link != null) it.clickable { host.open(link) } else it },
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
                    ) {
                        Column(Modifier.padding(12.dp)) {
                            Text(m.optString("label"), style = MaterialTheme.typography.labelMedium, color = muted(),
                                maxLines = 2, overflow = TextOverflow.Ellipsis)
                            Text(m.optString("value"), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold,
                                color = toneColor(m.str("tone")) ?: MaterialTheme.colorScheme.onSurface, maxLines = 1,
                                overflow = TextOverflow.Ellipsis)
                            m.str("sub")?.let {
                                Text(it, style = MaterialTheme.typography.bodySmall, color = toneColor(m.str("sub_tone")) ?: muted(),
                                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
                repeat(cols - line.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun BigBlock(b: JSONObject) {
    Column {
        Text(b.optString("label"), style = MaterialTheme.typography.labelLarge, color = muted())
        Text(b.optString("value"), style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold,
            color = toneColor(b.str("tone")) ?: MaterialTheme.colorScheme.onSurface)
        b.str("sub")?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = muted()) }
    }
}

@Composable
private fun Badge(badge: JSONObject) {
    val color = toneColor(badge.str("tone")) ?: MaterialTheme.colorScheme.primary
    Surface(color = color.copy(alpha = 0.14f), shape = RoundedCornerShape(6.dp)) {
        Text(badge.optString("text"), Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun RowsBlock(b: JSONObject, host: BlockHost) {
    val items = b.list("items")
    if (items.isEmpty()) {
        b.str("empty")?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted()) }
        return
    }
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column {
            items.forEachIndexed { i, it ->
                if (i > 0) HorizontalDivider(Modifier.padding(horizontal = 12.dp))
                ItemRow(it, host)
            }
        }
    }
}

@Composable
private fun ItemRow(it: JSONObject, host: BlockHost) {
    val link = it.obj("open")
    val action = it.obj("action")
    val click: (() -> Unit)? = when {
        link != null -> ({ host.open(link) })
        action != null -> ({ host.run(action.optString("name"), action.obj("args") ?: JSONObject(), action.str("confirm")) })
        else -> null
    }
    Row(
        Modifier.fillMaxWidth().let { m -> if (click != null) m.clickable { click() } else m }.padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            it.obj("badge")?.let { badge -> Badge(badge) }
            Text(it.optString("title"), style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
            it.str("sub")?.let { s -> Text(s, style = MaterialTheme.typography.bodySmall, color = muted(), maxLines = 3, overflow = TextOverflow.Ellipsis) }
        }
        it.str("value")?.let { v ->
            Spacer(Modifier.width(8.dp))
            Text(v, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium,
                color = toneColor(it.str("tone")) ?: if (action != null) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)
        }
        if (link != null) Icon(Icons.Filled.ChevronRight, null, tint = muted())
    }
}

@Composable
private fun CardBlock(b: JSONObject, host: BlockHost) {
    val tone = toneColor(b.str("tone"))
    val link = b.obj("open")
    val collapsible = b.has("collapsed") && !b.isNull("collapsed")
    var collapsed by remember(b.toString()) { mutableStateOf(b.bool("collapsed")) }
    val base = MaterialTheme.colorScheme.surfaceContainerLow
    Card(colors = CardDefaults.cardColors(containerColor = tone?.copy(alpha = 0.08f)?.compositeOver(base) ?: base)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            b.str("title")?.let { title ->
                Row(
                    Modifier.fillMaxWidth().let { m ->
                        when {
                            collapsible -> m.clickable { collapsed = !collapsed }
                            link != null -> m.clickable { host.open(link) }
                            else -> m
                        }
                    },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (tone != null) Box(Modifier.size(width = 3.dp, height = 18.dp).background(tone, RoundedCornerShape(2.dp)))
                    if (tone != null) Spacer(Modifier.width(8.dp))
                    Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    when {
                        collapsible -> Icon(if (collapsed) Icons.Filled.ExpandMore else Icons.Filled.ExpandLess, null, tint = muted())
                        link != null -> Icon(Icons.Filled.ChevronRight, null, tint = muted())
                    }
                }
            }
            if (!collapsible || !collapsed) b.list("blocks").forEach { Block(it, host) }
        }
    }
}

@Composable
private fun TableBlock(b: JSONObject) {
    val columns = b.strings("columns")
    val rows = (0 until (b.optJSONArray("rows")?.length() ?: 0)).map { i -> b.optJSONArray("rows")!!.optJSONArray(i) }
    val tones = b.optJSONArray("tones")
    val widths = columns.indices.map { c ->
        val longest = max(columns[c].length, rows.maxOfOrNull { r -> r?.optString(c)?.length ?: 0 } ?: 0)
        min(220, max(44, longest * 7 + 12)).dp
    }
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 6.dp)) {
            Row(Modifier.padding(horizontal = 8.dp)) {
                columns.forEachIndexed { c, h ->
                    Text(h, Modifier.width(widths[c]).padding(4.dp), style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold, color = muted())
                }
            }
            rows.forEachIndexed { i, r ->
                val bg = if (i % 2 == 0) Color.Transparent else MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.5f)
                Row(Modifier.background(bg).padding(horizontal = 8.dp)) {
                    columns.indices.forEach { c ->
                        val tone = tones?.optJSONArray(i)?.let { t -> if (t.isNull(c)) null else t.optString(c) }
                        Text(r?.optString(c) ?: "", Modifier.width(widths[c]).padding(4.dp), style = MaterialTheme.typography.bodySmall,
                            color = toneColor(tone) ?: MaterialTheme.colorScheme.onSurface)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChoiceBlock(b: JSONObject, host: BlockHost) {
    val name = b.optString("name")
    val value = b.opt("value")
    Column {
        b.str("label")?.let { Text(it, style = MaterialTheme.typography.labelMedium, color = muted()) }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            b.list("options").forEach { o ->
                val v = o.opt("value")
                FilterChip(
                    selected = same(v, value),
                    onClick = { if (!same(v, value)) host.mergeArgs(JSONObject().put(name, v)) },
                    label = { Text(o.optString("label"), maxLines = 1) },
                )
            }
        }
    }
}

@Composable
private fun PagerBlock(b: JSONObject, host: BlockHost) {
    val prev = b.obj("prev")
    val next = b.obj("next")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { prev?.let(host.mergeArgs) }, enabled = prev != null) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Précédent")
        }
        Text(b.optString("label"), Modifier.weight(1f), textAlign = TextAlign.Center, style = MaterialTheme.typography.titleSmall)
        IconButton(onClick = { next?.let(host.mergeArgs) }, enabled = next != null) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, "Suivant")
        }
    }
}

@Composable
private fun ButtonBlock(b: JSONObject, host: BlockHost, modifier: Modifier = Modifier.fillMaxWidth()) {
    val click = { host.run(b.optString("action"), b.obj("args") ?: JSONObject(), b.str("confirm")) }
    val label: @Composable () -> Unit = {
        kitIcon(b.str("icon"))?.let {
            Icon(it, null, Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
        }
        Text(b.optString("label"))
    }
    when (b.optString("style")) {
        "secondary" -> OutlinedButton(onClick = click, enabled = !host.busy, modifier = modifier) { label() }
        "text" -> TextButton(onClick = click, enabled = !host.busy, modifier = modifier) { label() }
        "danger" -> Button(onClick = click, enabled = !host.busy, modifier = modifier,
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { label() }
        else -> Button(onClick = click, enabled = !host.busy, modifier = modifier) { label() }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ButtonsBlock(b: JSONObject, host: BlockHost) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        b.list("items").forEach { ButtonBlock(it, host, Modifier) }
    }
}

@Composable
private fun SyncBlock(b: JSONObject) {
    val sync = LocalSync.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (sync.running) {
            Text(b.optString("running", "Synchronisation en cours…"), style = MaterialTheme.typography.bodySmall, color = muted())
            LinearProgressIndicator(Modifier.fillMaxWidth())
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(b.str("last")?.let { "Dernière synchro : $it" } ?: "Pas encore synchronisé.", Modifier.weight(1f),
                    style = MaterialTheme.typography.bodySmall, color = muted())
                TextButton(onClick = sync.start) {
                    kitIcon("sync")?.let { Icon(it, null, Modifier.size(18.dp)) }
                    Spacer(Modifier.width(4.dp))
                    Text("Synchroniser")
                }
            }
        }
    }
}

// ---- forms ----------------------------------------------------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FormBlock(b: JSONObject, host: BlockHost) {
    val fields = b.list("fields")
    val values = remember(b.toString()) {
        mutableStateMapOf<String, Any?>().apply {
            fields.forEach { f ->
                val name = f.optString("name")
                put(name, when (f.optString("kind")) {
                    "toggle" -> f.bool("value")
                    "select" -> if (f.isNull("value")) null else f.opt("value")
                    "multi" -> f.optJSONArray("value")?.let { a -> (0 until a.length()).map { a.get(it) } } ?: emptyList<Any>()
                    else -> if (!f.has("value") || f.isNull("value")) "" else f.get("value").toString()
                })
            }
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        fields.forEach { f -> Field(f, values[f.optString("name")]) { values[f.optString("name")] = it } }
        Button(
            onClick = {
                val out = JSONObject()
                fields.forEach { f ->
                    val name = f.optString("name")
                    when (val v = values[name]) {
                        is List<*> -> out.put(name, JSONArray(v))
                        null -> out.put(name, JSONObject.NULL)
                        else -> out.put(name, v)
                    }
                }
                if (b.bool("live")) host.mergeArgs(out)
                else host.run(b.optString("action"), (b.obj("args") ?: JSONObject()).merged(out), b.str("confirm"))
            },
            enabled = !host.busy,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(b.optString("submit", "Enregistrer")) }
    }
}

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun Field(f: JSONObject, value: Any?, onChange: (Any?) -> Unit) {
    val label = f.optString("label")
    val help = f.str("help")
    when (val kind = f.optString("kind", "text")) {
        "toggle" -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(label, style = MaterialTheme.typography.bodyMedium)
                help?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted()) }
            }
            Switch(checked = value == true, onCheckedChange = { onChange(it) })
        }
        "select" -> {
            var open by remember { mutableStateOf(false) }
            val options = f.list("options")
            val current = options.firstOrNull { same(it.opt("value"), value) }?.optString("label") ?: "—"
            Column {
                Text(label, style = MaterialTheme.typography.labelMedium, color = muted())
                Box {
                    OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
                        Text(current, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Icon(Icons.Filled.ArrowDropDown, null)
                    }
                    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                        options.forEach { o ->
                            DropdownMenuItem(text = { Text(o.optString("label")) }, onClick = {
                                onChange(o.opt("value"))
                                open = false
                            })
                        }
                    }
                }
                help?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted()) }
            }
        }
        "multi" -> Column {
            Text(label, style = MaterialTheme.typography.labelMedium, color = muted())
            val chosen = (value as? List<*>) ?: emptyList<Any>()
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                f.list("options").forEach { o ->
                    val v = o.opt("value")
                    val on = chosen.any { same(it, v) }
                    FilterChip(selected = on, onClick = {
                        onChange(if (on) chosen.filterNot { same(it, v) } else chosen + v)
                    }, label = { Text(o.optString("label")) })
                }
            }
        }
        else -> {
            val hint = f.str("placeholder") ?: when (kind) {
                "date" -> "AAAA-MM-JJ"
                "time" -> "HH:MM"
                else -> null
            }
            val placeholder: (@Composable () -> Unit)? = hint?.let { t -> @Composable { Text(t) } }
            val supporting: (@Composable () -> Unit)? = help?.let { t -> @Composable { Text(t) } }
            OutlinedTextField(
            value = value as? String ?: "",
            onValueChange = { onChange(it) },
            label = { Text(label) },
            placeholder = placeholder,
            supportingText = supporting,
            singleLine = kind != "multiline",
            minLines = if (kind == "multiline") 3 else 1,
            visualTransformation = if (kind == "secret") PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = when (kind) {
                "number" -> KeyboardType.Number
                "decimal" -> KeyboardType.Decimal
                "secret" -> KeyboardType.Password
                else -> KeyboardType.Text
            }),
            modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
