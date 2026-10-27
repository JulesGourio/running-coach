package fr.julesgourio.coach

import android.app.Application
import fr.julesgourio.kit.Kit
import fr.julesgourio.kit.KitConfig

/** Everything the app does is in Python (`coach.mobile`); this only names it for the kit. */
class CoachApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Kit.init(
            this,
            KitConfig(
                pythonModule = "coach.mobile",
                appName = getString(R.string.app_name),
                notificationIcon = R.drawable.ic_notification,
                syncHour = 7,
                syncMinute = 15,
                lockSubtitle = "Déverrouille pour voir ton entraînement",
                secretAlias = "coach-secrets",
            ),
        )
    }
}
