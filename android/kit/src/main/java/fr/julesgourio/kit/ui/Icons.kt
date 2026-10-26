package fr.julesgourio.kit.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.filled.Help
import androidx.compose.material.icons.automirrored.filled.Login
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.MonitorHeart
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material.icons.filled.Today
import androidx.compose.material.icons.filled.Watch
import androidx.compose.ui.graphics.vector.ImageVector

/** Icon names usable from Python (tabs and buttons). */
fun kitIcon(name: String?): ImageVector? = when (name) {
    "today" -> Icons.Filled.Today
    "run" -> Icons.AutoMirrored.Filled.DirectionsRun
    "calendar" -> Icons.Filled.CalendarMonth
    "trend" -> Icons.AutoMirrored.Filled.TrendingUp
    "chart" -> Icons.AutoMirrored.Filled.ShowChart
    "heart" -> Icons.Filled.MonitorHeart
    "bed" -> Icons.Filled.Bedtime
    "history" -> Icons.Filled.History
    "fitness" -> Icons.Filled.FitnessCenter
    "flag" -> Icons.Filled.Flag
    "help" -> Icons.AutoMirrored.Filled.Help
    "settings" -> Icons.Filled.Settings
    "more" -> Icons.Filled.MoreHoriz
    "home" -> Icons.Filled.Home
    "bank" -> Icons.Filled.AccountBalance
    "insights" -> Icons.Filled.Insights
    "receipt" -> Icons.AutoMirrored.Filled.ReceiptLong
    "bell" -> Icons.Filled.Notifications
    "person" -> Icons.Filled.Person
    "sync" -> Icons.Filled.Sync
    "refresh" -> Icons.Filled.Refresh
    "upload" -> Icons.Filled.CloudUpload
    "download" -> Icons.Filled.Download
    "delete" -> Icons.Filled.Delete
    "login" -> Icons.AutoMirrored.Filled.Login
    "watch" -> Icons.Filled.Watch
    else -> null
}
