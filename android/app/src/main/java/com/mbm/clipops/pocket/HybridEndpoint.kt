package com.mbm.clipops.pocket

import java.net.URI

/** User-configured private endpoints, never public arbitrary URLs or LAN cleartext. */
internal object HybridEndpoint {
    enum class Engine { LAPTOP, CLOUD, DEV_TUNNEL }
    private val dnsLabel = Regex("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")

    fun validated(input: String, engine: Engine): String {
        require(input.length in 1..253 && input == input.trim()) {
            "Enter a private HTTPS Studio URL without spaces."
        }
        val url = try { URI(input) }
                  catch (_: Exception) { throw IllegalArgumentException("Enter a valid HTTPS URL.") }
        require(url.scheme == "https" && url.rawUserInfo == null && url.port == -1 &&
                url.rawQuery == null && url.rawFragment == null &&
                (url.rawPath.isNullOrEmpty() || url.rawPath == "/")) {
            "Use the exact HTTPS host, without ports, passwords, paths, parameters or fragments."
        }
        val host = url.host ?: throw IllegalArgumentException("Missing private Studio hostname.")
        require(host == host.lowercase() && host.isNotEmpty() && host.length <= 253) {
            "Use the lowercase DNS hostname."
        }
        val labels = host.split(".")
        require(labels.all { dnsLabel.matches(it) }) {
            "Invalid private DNS hostname."
        }
        when(engine) {
            Engine.LAPTOP -> require(labels.size == 4 && labels.takeLast(2) == listOf("ts","net")) {
                "Laptop Studio must use the private device.tailnet.ts.net HTTPS address."
            }
            Engine.CLOUD -> require(labels.size >= 3 &&
                    labels.takeLast(2) == listOf("cloudshell","dev") &&
                    labels.first().startsWith("8080-") && labels.first().length > 5) {
                "Cloud Studio must use the private https://8080-...cloudshell.dev preview address."
            }
            Engine.DEV_TUNNEL -> require(labels.size == 4 &&
                    labels.takeLast(2) == listOf("devtunnels","ms") &&
                    Regex("[a-z0-9][a-z0-9-]{1,55}-8765").matches(labels[0])) {
                "Use the signed-in Microsoft Dev Tunnel HTTPS URL ending -8765.region.devtunnels.ms."
            }
        }
        return "https://$host/"
    }
}
