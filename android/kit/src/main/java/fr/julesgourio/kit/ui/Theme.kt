package fr.julesgourio.kit.ui

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

/** Fixed, readable colours for tones, whatever the wallpaper colours are. */
@Immutable
data class Tones(val good: Color, val bad: Color, val warn: Color, val info: Color)

val LocalTones = staticCompositionLocalOf { Tones(Color(0xFF1A7F37), Color(0xFFCF222E), Color(0xFFC9750A), Color(0xFF2E6FDB)) }

@Composable
fun KitTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val context = LocalContext.current
    val colors = when {
        Build.VERSION.SDK_INT >= 31 -> if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        dark -> darkColorScheme()
        else -> lightColorScheme(primary = Color(0xFF2E6FDB))
    }
    val tones = if (dark) Tones(Color(0xFF6FD6A4), Color(0xFFFF8A80), Color(0xFFFFC266), Color(0xFF8AB4F8))
    else Tones(Color(0xFF1A7F37), Color(0xFFCF222E), Color(0xFFC9750A), Color(0xFF2E6FDB))
    CompositionLocalProvider(LocalTones provides tones) {
        MaterialTheme(colorScheme = colors, content = content)
    }
}

/** "good", "bad", "warn", "info", "muted" or "#rrggbb"; null when unknown. */
@Composable
fun toneColor(tone: String?): Color? {
    val t = LocalTones.current
    return when (tone) {
        null, "" -> null
        "good" -> t.good
        "bad" -> t.bad
        "warn" -> t.warn
        "info" -> t.info
        "muted" -> MaterialTheme.colorScheme.onSurfaceVariant
        else -> parseHex(tone)
    }
}

fun parseHex(hex: String?): Color? = try {
    if (hex == null || !hex.startsWith("#")) null else Color(android.graphics.Color.parseColor(hex))
} catch (e: IllegalArgumentException) {
    null
}
