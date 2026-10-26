package fr.julesgourio.kit.ui

import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.MainScope
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicLong

/** A screen of the Python app with its arguments; [cached] keeps the last page to show it again at once. */
class Dest(val screen: String, val args: JSONObject = JSONObject()) {
    val key: Long = counter.incrementAndGet()
    var cached: JSONObject? = null

    companion object {
        private val counter = AtomicLong()
    }
}

/** The web sign-in page (`Result.webauth`): url, prefix, finish, title. */
const val WEBAUTH = "__webauth"

/** One back stack per tab, as in most phone apps. */
class KitNav(tabs: List<String>) {
    var tab by mutableStateOf(tabs.firstOrNull() ?: "")
        private set
    private val stacks = mutableStateMapOf<String, List<Dest>>()

    init {
        tabs.forEach { stacks[it] = listOf(Dest(it)) }
    }

    val stack: List<Dest> get() = stacks[tab] ?: emptyList()
    val current: Dest? get() = stack.lastOrNull()

    fun push(d: Dest) {
        stacks[tab] = stack + d
    }

    fun pop(): Boolean {
        if (stack.size <= 1) return false
        stacks[tab] = stack.dropLast(1)
        return true
    }

    /** Same screen with other arguments (a choice, a pager, a live form), in place. */
    fun replaceTop(d: Dest) {
        stacks[tab] = stack.dropLast(1) + d
    }

    /** Tapping the current tab again goes back to its first screen. */
    fun selectTab(t: String) {
        if (t == tab) stacks[t] = stack.take(1) else tab = t
    }
}

/** Whether a sync runs, and how to start one (provided by KitActivity). */
class SyncState(val running: Boolean, val start: () -> Unit)

val LocalNav = staticCompositionLocalOf<KitNav> { error("KitNav manquant") }
val LocalRefresh = staticCompositionLocalOf { 0 }
val LocalSync = staticCompositionLocalOf { SyncState(false) {} }
val LocalSnackbar = staticCompositionLocalOf { SnackbarHostState() }

/** Outlives screens: messages and sign-in results keep going when the screen that started them closes. */
val LocalAppScope = staticCompositionLocalOf<CoroutineScope> { MainScope() }
