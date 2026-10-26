package fr.julesgourio.kit.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min

private data class Series(val name: String, val values: List<Double?>, val color: Color, val style: String)

private data class Band(val from: Double, val to: Double, val color: Color, val label: String?)

private data class HLine(val y: Double, val label: String?, val color: Color)

@Composable
private fun palette(): List<Color> = listOf(
    MaterialTheme.colorScheme.primary, Color(0xFFD9480F), Color(0xFF1A7F37), Color(0xFF7C3AED),
    Color(0xFFDB2777), Color(0xFF0D9488), Color(0xFFCA8A04), Color(0xFF64748B),
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChartBlock(b: JSONObject) {
    val kind = b.optString("kind", "line")
    val labels = b.strings("labels")
    val colors = palette()
    val series = b.list("series").mapIndexed { i, s ->
        Series(s.optString("name"), s.optJSONArray("values").doubles(), parseHex(s.str("color")) ?: colors[i % colors.size],
            s.optString("style", if (kind == "line") "line" else "bar"))
    }
    val y = b.optString("y", "num")
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    var selected by remember(b.toString()) { mutableStateOf<Int?>(null) }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        b.str("title")?.let { Text(it, style = MaterialTheme.typography.titleSmall) }
        if (labels.isEmpty() || series.isEmpty()) {
            Text("Pas de données.", style = MaterialTheme.typography.bodySmall, color = muted)
            return
        }
        if (kind == "hbar") {
            HBars(labels, series.first(), y)
            return
        }
        val sel = selected
        val readout = if (sel != null && sel in labels.indices) {
            labels[sel] + " · " + series.mapNotNull { s -> s.values.getOrNull(sel)?.let { "${s.name} ${formatValue(it, y)}" } }
                .joinToString(" · ")
        } else "Touche le graphique pour lire une valeur."
        Text(readout, style = MaterialTheme.typography.labelSmall, color = muted, maxLines = 2, overflow = TextOverflow.Ellipsis)
        XYChart(b, kind, labels, series, y, sel) { selected = it }
        if (series.size > 1 || b.list("bands").any { it.str("label") != null }) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                series.forEach { s -> Legend(s.color, s.name) }
            }
        }
    }
}

@Composable
private fun Legend(color: Color, name: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(color, CircleShape))
        Spacer(Modifier.width(4.dp))
        Text(name, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun XYChart(
    b: JSONObject, kind: String, labels: List<String>, series: List<Series>, y: String, selected: Int?, onSelect: (Int?) -> Unit,
) {
    val measurer = rememberTextMeasurer()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val grid = MaterialTheme.colorScheme.outlineVariant
    val highlightColor = MaterialTheme.colorScheme.primary
    val n = labels.size
    val reverse = b.bool("reverse")
    val bands = b.list("bands").map { Band(it.optDouble("from"), it.optDouble("to"), parseHex(it.str("color")) ?: highlightColor, it.str("label")) }
    val lines = b.list("lines").map { HLine(it.optDouble("y"), it.str("label"), parseHex(it.str("color")) ?: grid) }
    val stacked = kind == "stack"
    val barSeries = if (stacked) series else series.filter { it.style == "bar" }
    val overlay = if (stacked) emptyList() else series.filter { it.style != "bar" }
    val barsLayout = kind != "line" || barSeries.isNotEmpty()
    val highlight = if (b.has("highlight") && !b.isNull("highlight")) b.optInt("highlight") else null

    // value range
    val values = mutableListOf<Double>()
    if (stacked) {
        for (i in 0 until n) values += series.sumOf { (it.values.getOrNull(i) ?: 0.0).coerceAtLeast(0.0) }
        values += 0.0
    } else {
        series.forEach { s -> s.values.forEach { v -> if (v != null) values += v } }
        if (barSeries.isNotEmpty()) values += 0.0
    }
    lines.forEach { values += it.y }
    val fixedLo = b.num("y_min")
    val fixedHi = b.num("y_max")
    var lo = fixedLo ?: values.minOrNull() ?: 0.0
    var hi = fixedHi ?: values.maxOrNull() ?: 1.0
    val span = hi - lo
    val pad = if (span > 0) span * 0.06 else max(abs(hi) * 0.1, 1.0)
    if (fixedLo == null && !(lo == 0.0 && barSeries.isNotEmpty())) lo -= pad // bars stand on zero
    if (fixedHi == null) hi += pad
    if (hi <= lo) hi = lo + 1.0

    val height = b.optInt("height", 180).coerceIn(80, 400)
    Canvas(
        Modifier.fillMaxWidth().height(height.dp).pointerInput(labels, barsLayout) {
            detectTapGestures { off ->
                val left = 44.dp.toPx()
                val w = size.width - left - 8.dp.toPx()
                val i = if (barsLayout) ((off.x - left) / (w / n)).toInt()
                else if (n == 1) 0 else ((off.x - left) / (w / (n - 1)) + 0.5f).toInt()
                onSelect(if (i in 0 until n) i else null)
            }
        },
    ) {
        val left = 44.dp.toPx()
        val right = 8.dp.toPx()
        val top = 4.dp.toPx()
        val bottom = 18.dp.toPx()
        val w = size.width - left - right
        val h = size.height - top - bottom
        fun xAt(i: Int): Float = left + if (barsLayout) (i + 0.5f) * w / n else if (n == 1) w / 2 else i * w / (n - 1)
        fun yAt(v: Double): Float {
            val f = ((v - lo) / (hi - lo)).toFloat().coerceIn(-0.05f, 1.05f)
            return top + (if (reverse) f else 1f - f) * h
        }

        // grid and y labels
        for (k in 0..2) {
            val v = lo + (hi - lo) * k / 2
            val yy = yAt(v)
            drawLine(grid, Offset(left, yy), Offset(left + w, yy), strokeWidth = 1f)
            val t = formatValue(v, y)
            val tw = measurer.measure(t, labelStyle).size
            drawText(measurer, t, Offset(left - tw.width - 4.dp.toPx(), yy - tw.height / 2f), labelStyle)
        }
        // highlighted column (current week…) and selection
        listOfNotNull(highlight, selected).distinct().forEach { i ->
            if (i in 0 until n) {
                val cw = if (barsLayout) w / n else max(w / max(n - 1, 1), 6.dp.toPx())
                drawRect(highlightColor.copy(alpha = if (i == selected) 0.14f else 0.07f), Offset(xAt(i) - cw / 2, top), Size(cw, h))
            }
        }
        // bands
        bands.forEach { bd ->
            val a = yAt(max(min(bd.from, bd.to), lo))
            val c = yAt(min(max(bd.from, bd.to), hi))
            drawRect(bd.color.copy(alpha = 0.12f), Offset(left, min(a, c)), Size(w, abs(a - c)))
        }
        // bars
        if (barSeries.isNotEmpty()) {
            val slot = w / n
            if (stacked) {
                val bw = slot * 0.7f
                for (i in 0 until n) {
                    var base = 0.0
                    barSeries.forEach { s ->
                        val v = (s.values.getOrNull(i) ?: 0.0).coerceAtLeast(0.0)
                        if (v > 0) {
                            val y0 = yAt(base)
                            val y1 = yAt(base + v)
                            drawRect(s.color, Offset(xAt(i) - bw / 2, min(y0, y1)), Size(bw, abs(y0 - y1)))
                        }
                        base += v
                    }
                }
            } else {
                val group = slot * 0.75f
                val bw = group / barSeries.size
                barSeries.forEachIndexed { k, s ->
                    for (i in 0 until n) {
                        val v = s.values.getOrNull(i) ?: continue
                        val y0 = yAt(0.0.coerceIn(lo, hi))
                        val y1 = yAt(v)
                        val x = xAt(i) - group / 2 + k * bw
                        drawRect(if (v < 0) s.color.copy(alpha = 0.7f) else s.color, Offset(x, min(y0, y1)), Size(bw * 0.92f, max(abs(y0 - y1), 1f)))
                    }
                }
            }
        }
        // lines, areas, points
        overlay.forEach { s -> drawSeries(s, n, ::xAt, ::yAt, top + h, selected) }
        // reference lines
        lines.forEach { ln ->
            val yy = yAt(ln.y)
            drawLine(ln.color, Offset(left, yy), Offset(left + w, yy), strokeWidth = 1.5.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)))
            ln.label?.let {
                val st = labelStyle.copy(color = ln.color)
                val tw = measurer.measure(it, st).size
                drawText(measurer, it, Offset(left + w - tw.width, yy - tw.height - 1f), st)
            }
        }
        // x labels: first, middle, last
        val idx = listOf(0, n / 2, n - 1).distinct().filter { it in 0 until n }
        idx.forEach { i ->
            val t = labels[i]
            val tw = measurer.measure(t, labelStyle).size.width
            val x = (xAt(i) - tw / 2f).coerceIn(left, left + w - tw)
            drawText(measurer, t, Offset(x, top + h + 3.dp.toPx()), labelStyle)
        }
    }
}

private fun DrawScope.drawSeries(
    s: Series, n: Int, xAt: (Int) -> Float, yAt: (Double) -> Float, floor: Float, selected: Int?,
) {
    val pts = (0 until n).map { i -> s.values.getOrNull(i)?.let { Offset(xAt(i), yAt(it)) } }
    if (s.style == "points") {
        pts.forEachIndexed { i, p -> if (p != null) drawCircle(s.color, if (i == selected) 6.dp.toPx() else 3.5.dp.toPx(), p) }
        // a light line between points shows the trend
        drawPolyline(pts, s.color.copy(alpha = 0.35f), 1.dp.toPx(), null)
        return
    }
    if (s.style == "area") {
        var seg = mutableListOf<Offset>()
        fun flush() {
            if (seg.size >= 2) {
                val path = Path().apply {
                    moveTo(seg.first().x, floor)
                    seg.forEach { lineTo(it.x, it.y) }
                    lineTo(seg.last().x, floor)
                    close()
                }
                drawPath(path, s.color.copy(alpha = 0.22f))
            }
            seg = mutableListOf()
        }
        pts.forEach { p -> if (p == null) flush() else seg += p }
        flush()
    }
    val effect = if (s.style == "dash") PathEffect.dashPathEffect(floatArrayOf(12f, 8f)) else null
    drawPolyline(pts, s.color, 2.dp.toPx(), effect)
    if (pts.count { it != null } == 1 || n <= 12) {
        pts.forEach { p -> if (p != null) drawCircle(s.color, 2.5.dp.toPx(), p) }
    }
    selected?.let { i -> pts.getOrNull(i)?.let { drawCircle(s.color, 5.dp.toPx(), it) } }
}

private fun DrawScope.drawPolyline(pts: List<Offset?>, color: Color, width: Float, effect: PathEffect?) {
    val path = Path()
    var open = false
    pts.forEach { p ->
        if (p == null) {
            open = false
        } else if (!open) {
            path.moveTo(p.x, p.y)
            open = true
        } else {
            path.lineTo(p.x, p.y)
        }
    }
    drawPath(path, color, style = Stroke(width = width, cap = StrokeCap.Round, pathEffect = effect))
}

@Composable
private fun HBars(labels: List<String>, s: Series, y: String) {
    val maxV = (if (y == "pct") 100.0 else s.values.filterNotNull().maxOrNull() ?: 1.0).coerceAtLeast(1e-9)
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        labels.forEachIndexed { i, label ->
            val v = s.values.getOrNull(i)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(label, Modifier.width(110.dp), style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Box(Modifier.weight(1f).height(14.dp)) {
                    val f = ((v ?: 0.0) / maxV).toFloat().coerceIn(0f, 1f)
                    if (f > 0f) {
                        Box(Modifier.fillMaxWidth(f).fillMaxHeight().background(s.color, RoundedCornerShape(3.dp)))
                    }
                }
                Text(v?.let { formatValue(it, y) } ?: "—", Modifier.width(56.dp).padding(start = 6.dp),
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/** A GPS track drawn on its own (no map tiles), start in green and finish in red. */
@Composable
fun RouteBlock(b: JSONObject) {
    val arr = b.optJSONArray("points") ?: return
    val pts = (0 until arr.length()).mapNotNull { i ->
        arr.optJSONArray(i)?.let { p -> if (p.length() >= 2) p.optDouble(0) to p.optDouble(1) else null }
    }.filter { !it.first.isNaN() && !it.second.isNaN() }
    if (pts.size < 2) return
    val line = MaterialTheme.colorScheme.primary
    val tones = LocalTones.current
    Column {
        Canvas(Modifier.fillMaxWidth().height(b.optInt("height", 220).dp)) {
            val lat0 = pts.minOf { it.first }
            val lat1 = pts.maxOf { it.first }
            val lon0 = pts.minOf { it.second }
            val lon1 = pts.maxOf { it.second }
            val k = cos(Math.toRadians((lat0 + lat1) / 2))
            val spanX = max((lon1 - lon0) * k, 1e-6)
            val spanY = max(lat1 - lat0, 1e-6)
            val pad = 10.dp.toPx()
            val scale = min((size.width - 2 * pad) / spanX, (size.height - 2 * pad) / spanY)
            val offX = (size.width - spanX * scale) / 2
            val offY = (size.height - spanY * scale) / 2
            fun at(p: Pair<Double, Double>) = Offset((offX + (p.second - lon0) * k * scale).toFloat(), (offY + (lat1 - p.first) * scale).toFloat())
            val path = Path().apply {
                val first = at(pts.first())
                moveTo(first.x, first.y)
                pts.drop(1).forEach { val o = at(it); lineTo(o.x, o.y) }
            }
            drawPath(path, line, style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round))
            drawCircle(tones.good, 5.dp.toPx(), at(pts.first()))
            drawCircle(tones.bad, 5.dp.toPx(), at(pts.last()))
        }
        b.str("label")?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
