package fr.julesgourio.kit.engine

import org.json.JSONObject

/** What every Python bridge function returns: `{"ok": true, "data": …}` or `{"ok": false, "erreur": "…"}`. */
sealed interface Reply {
    data class Ok(val data: Any?) : Reply
    data class Err(val message: String) : Reply

    val json: JSONObject? get() = (this as? Ok)?.data as? JSONObject

    companion object {
        fun parse(raw: String): Reply = try {
            val o = JSONObject(raw)
            if (o.optBoolean("ok")) Ok(o.opt("data").takeUnless { it == JSONObject.NULL })
            else Err(o.optString("erreur").ifBlank { "erreur inconnue" })
        } catch (e: Exception) {
            Err("réponse illisible : ${e.message}")
        }
    }
}
