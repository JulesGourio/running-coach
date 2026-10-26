package fr.julesgourio.kit.work

import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import fr.julesgourio.kit.Kit
import fr.julesgourio.kit.engine.Engine
import fr.julesgourio.kit.engine.Notifier
import fr.julesgourio.kit.engine.Reply
import org.json.JSONObject

/** The app's background sync (`app.on_sync` in Python), daily and on demand. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        try {
            setForeground(getForegroundInfo())
        } catch (e: Exception) {
            // Android may refuse a foreground job from the background: the sync still runs, with less time.
        }
        return when (val reply = Engine.sync()) {
            is Reply.Ok -> {
                val lines = (reply.data as? JSONObject)?.optJSONArray("lignes")
                val text = (0 until (lines?.length() ?: 0)).joinToString("\n") { lines!!.optString(it) }
                Result.success(workDataOf(KEY_LINES to text.take(8000)))
            }
            is Reply.Err ->
                if (runAttemptCount < 2) Result.retry() else Result.failure(workDataOf(KEY_ERROR to reply.message))
        }
    }

    override suspend fun getForegroundInfo(): ForegroundInfo {
        val n = NotificationCompat.Builder(applicationContext, Notifier.SYNC)
            .setSmallIcon(Kit.config.notificationIcon)
            .setContentTitle(Kit.config.appName)
            .setContentText("Synchronisation…")
            .setOngoing(true)
            .setSilent(true)
            .build()
        return if (Build.VERSION.SDK_INT >= 29) {
            ForegroundInfo(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(NOTIFICATION_ID, n)
        }
    }

    companion object {
        const val KEY_LINES = "lignes"
        const val KEY_ERROR = "erreur"
        private const val NOTIFICATION_ID = 7_30
    }
}
