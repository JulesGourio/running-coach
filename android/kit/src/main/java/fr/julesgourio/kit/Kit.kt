package fr.julesgourio.kit

import android.app.Application
import fr.julesgourio.kit.engine.Engine
import fr.julesgourio.kit.engine.Notifier
import fr.julesgourio.kit.work.Scheduler

/**
 * What differs from one app to the next. Everything else (screens, actions, tabs) comes from the app's
 * Python module, which declares `app = appkit.App(...)`.
 */
data class KitConfig(
    /** The Python module that defines `app`, e.g. "coach.mobile". */
    val pythonModule: String,
    val appName: String,
    /** Monochrome icon for notifications (R.drawable.… of the app). */
    val notificationIcon: Int,
    /** Daily background sync, local time. */
    val syncHour: Int = 7,
    val syncMinute: Int = 30,
    /** Fingerprint or device code after five minutes away. */
    val lock: Boolean = true,
    val lockSubtitle: String = "Déverrouille pour continuer",
    /** Android Keystore alias of the key that encrypts the app's secrets. */
    val secretAlias: String = "kit-secrets",
)

object Kit {
    lateinit var config: KitConfig
        private set
    lateinit var app: Application
        private set

    /** Call from Application.onCreate. */
    fun init(app: Application, config: KitConfig) {
        this.app = app
        this.config = config
        Engine.attach(app)
        Notifier.createChannels(app)
        Scheduler.ensure(app)
    }
}
