package fr.julesgourio.kit.engine

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import fr.julesgourio.kit.Kit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * The app's Python engine, started once per process on first use (`appkit.bridge.start`).
 * Every call runs off the main thread and comes back as a [Reply].
 */
object Engine {
    private lateinit var context: Context
    private val startLock = Mutex()

    @Volatile
    private var bridge: PyObject? = null

    @Volatile
    var manifest: JSONObject? = null
        private set

    fun attach(context: Context) {
        this.context = context.applicationContext
    }

    val dataDir: File get() = File(context.filesDir, "data")
    val cacheDir: File get() = context.cacheDir

    private suspend fun ensureBridge(): PyObject = bridge ?: startLock.withLock {
        bridge ?: run {
            if (!Python.isStarted()) Python.start(AndroidPlatform(context))
            val b = Python.getInstance().getModule("appkit.bridge")
            val reply = Reply.parse(
                b.callAttr(
                    "start", Kit.config.pythonModule, dataDir.absolutePath,
                    SecretStore(context, Kit.config.secretAlias), Notifier(context),
                ).toString(),
            )
            when (reply) {
                is Reply.Err -> throw IllegalStateException("démarrage du moteur : ${reply.message}")
                is Reply.Ok -> manifest = reply.data as? JSONObject
            }
            b.also { bridge = it }
        }
    }

    private suspend fun invoke(function: String, vararg args: Any?): Reply = withContext(Dispatchers.IO) {
        try {
            Reply.parse(ensureBridge().callAttr(function, *args).toString())
        } catch (e: Throwable) {
            Reply.Err(e.message ?: e.toString())
        }
    }

    /** Starts Python if needed and returns the app's manifest (title, tabs). */
    suspend fun start(): Reply = withContext(Dispatchers.IO) {
        try {
            ensureBridge()
            Reply.Ok(manifest)
        } catch (e: Throwable) {
            Reply.Err(e.message ?: e.toString())
        }
    }

    suspend fun screen(name: String, args: JSONObject): Reply = invoke("screen", name, args.toString())
    suspend fun action(name: String, args: JSONObject): Reply = invoke("action", name, args.toString())
    suspend fun sync(): Reply = invoke("sync")
}
