package fr.julesgourio.kit.engine

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import fr.julesgourio.kit.Kit
import java.util.concurrent.atomic.AtomicInteger

/** The phone's notifications for Python (`notify` handlers). Python calls [show]. */
class Notifier(private val context: Context) {

    fun show(title: String, message: String, priority: Int): Boolean {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return false
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val open = launch?.let { PendingIntent.getActivity(context, 0, it, PendingIntent.FLAG_IMMUTABLE) }
        val urgent = priority >= 4
        val n = NotificationCompat.Builder(context, if (urgent) URGENT else ALERTS)
            .setSmallIcon(Kit.config.notificationIcon)
            .setContentTitle(title)
            .setContentText(message.lineSequence().firstOrNull { it.isNotBlank() } ?: message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(if (urgent) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .apply { if (open != null) setContentIntent(open) }
            .build()
        return try {
            NotificationManagerCompat.from(context).notify(ids.incrementAndGet(), n)
            true
        } catch (e: SecurityException) {
            false
        }
    }

    companion object {
        const val ALERTS = "alertes"
        const val URGENT = "urgent"
        const val SYNC = "synchro"
        private val ids = AtomicInteger((System.currentTimeMillis() / 1000 % 100_000).toInt())

        fun createChannels(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannels(
                listOf(
                    NotificationChannel(ALERTS, "Alertes", NotificationManager.IMPORTANCE_DEFAULT),
                    NotificationChannel(URGENT, "À faire (connexions)", NotificationManager.IMPORTANCE_HIGH),
                    NotificationChannel(SYNC, "Synchronisation en cours", NotificationManager.IMPORTANCE_LOW),
                ),
            )
        }
    }
}
