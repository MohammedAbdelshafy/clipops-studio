package com.mbm.clipops.pocket

import java.net.URI

/**
 * Only explicit, private HTTPS backend addresses. Tailscale Serve is private
 * only when Funnel is OFF and the tailnet ACL allows this Android device.
 * The pairing code also protects Studio when other tailnet members exist.
 */
internal data class StudioEndpoint(val origin: String, val type: Type) {
    enum class Type { TAILNET, CLOUD_SHELL }

    fun permits(url: String): Boolean = try {
        val uri = URI(url)
        uri.scheme == "https" && uri.rawUserInfo == null && uri.port == -1 &&
            uri.host?.lowercase() == URI(origin).host && uri.rawFragment == null
    } catch (_: Exception) {
        false
    }

    companion object {
        private val DNS_LABEL = Regex("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
        private val CLOUD_PREFIX = Regex("8080-[a-z0-9-]+")

        fun parse(input: String): StudioEndpoint {
            val text = input.trim()
            require(text.length in 12..253 && text == input.trim()) {
                "Enter the private HTTPS address shown by your backend."
            }
            val uri = try { URI(text) } catch (_: Exception) {
                throw IllegalArgumentException("Enter a valid HTTPS endpoint.")
            }
            val host = uri.host?.lowercase() ?: throw IllegalArgumentException("Missing endpoint hostname.")
            val names = host.split('.')
            require(uri.scheme == "https" && uri.rawUserInfo == null && uri.port == -1 &&
                uri.rawQuery == null && uri.rawFragment == null &&
                uri.rawPath in listOf("", "/") && uri.rawAuthority == host &&
                names.all { DNS_LABEL.matches(it) }) {
                "Only an exact private HTTPS host without a port or path is accepted."
            }
            val kind = when {
                names.size >= 4 && names.takeLast(2) == listOf("ts", "net") -> Type.TAILNET
                names.size >= 4 && names.takeLast(2) == listOf("cloudshell", "dev") &&
                    CLOUD_PREFIX.matches(names.first()) -> Type.CLOUD_SHELL
                else -> throw IllegalArgumentException(
                    "Use a private Tailscale Serve *.ts.net URL or Cloud Shell 8080 preview."
                )
            }
            return StudioEndpoint("https://$host", kind)
        }
    }
}
