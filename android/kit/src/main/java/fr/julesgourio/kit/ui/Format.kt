package fr.julesgourio.kit.ui

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/** Chart axis values, by the `y` kind of a chart block. */
fun formatValue(v: Double, kind: String): String = when (kind) {
    "pace" -> clock(v)
    "time" -> clock(v)
    "pct" -> "${v.roundToInt()} %"
    "hours" -> {
        val m = (v * 60).roundToInt()
        "${m / 60} h ${"%02d".format(m % 60)}"
    }
    "km" -> if (abs(v) < 10) decimal(v, 1) + " km" else "${v.roundToInt()} km"
    "int" -> "${v.roundToInt()}"
    else -> if (abs(v) >= 100) "${v.roundToInt()}" else decimal(v, if (abs(v) < 10) 2 else 1)
}

fun decimal(v: Double, digits: Int): String {
    if (digits <= 0) return "${v.roundToInt()}"
    return String.format(Locale.FRANCE, "%.${digits}f", v).trimEnd('0').trimEnd(',').ifEmpty { "0" }
}

/** Seconds as m:ss or h:mm:ss. */
fun clock(v: Double): String {
    val s = v.roundToLong()
    val h = s / 3600
    val m = s % 3600 / 60
    val sec = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
}

/** Text with **bold** parts. */
fun rich(text: String): AnnotatedString = buildAnnotatedString {
    val parts = text.split("**")
    parts.forEachIndexed { i, part ->
        if (i % 2 == 1) withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(part) } else append(part)
    }
}
