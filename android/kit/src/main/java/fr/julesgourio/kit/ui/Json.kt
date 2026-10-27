package fr.julesgourio.kit.ui

import org.json.JSONArray
import org.json.JSONObject

// org.json turns JSON null into JSONObject.NULL and optString into "null": these helpers give real nulls.

fun JSONObject.str(key: String): String? =
    if (!has(key) || isNull(key)) null else optString(key).takeUnless { it.isEmpty() }

fun JSONObject.num(key: String): Double? =
    if (!has(key) || isNull(key)) null else optDouble(key).takeUnless { it.isNaN() }

fun JSONObject.bool(key: String): Boolean = has(key) && !isNull(key) && optBoolean(key)

fun JSONObject.obj(key: String): JSONObject? = if (!has(key) || isNull(key)) null else optJSONObject(key)

fun JSONObject.list(key: String): List<JSONObject> = optJSONArray(key).objects()

fun JSONObject.strings(key: String): List<String> = optJSONArray(key)?.let { a ->
    (0 until a.length()).map { i -> if (a.isNull(i)) "" else a.optString(i) }
} ?: emptyList()

fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

/** Numbers of an array, null where the value is null. */
fun JSONArray?.doubles(): List<Double?> =
    if (this == null) emptyList() else (0 until length()).map { i -> if (isNull(i)) null else optDouble(i).takeUnless { it.isNaN() } }

fun JSONObject.copy(): JSONObject = JSONObject(toString())

/** A copy of this object with the keys of [other] added or replaced. */
fun JSONObject.merged(other: JSONObject): JSONObject = copy().also { o -> other.keys().forEach { o.put(it, other.get(it)) } }

/** The same JSON value, whatever its Java type (for comparing option values). */
fun same(a: Any?, b: Any?): Boolean = when {
    a == null || a == JSONObject.NULL -> b == null || b == JSONObject.NULL
    a is Number && b is Number -> a.toDouble() == b.toDouble()
    else -> a.toString() == b?.toString()
}
