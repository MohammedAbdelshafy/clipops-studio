package com.mbm.clipops.pocket

import org.junit.Assert.assertEquals
import org.junit.Test

class HybridEndpointTest {
    @Test fun acceptsOnlyPrivateHttpsEngineUrls() {
        assertEquals("https://laptop.my-tailnet.ts.net/",
            HybridEndpoint.validated("https://laptop.my-tailnet.ts.net",
                HybridEndpoint.Engine.LAPTOP))
        assertEquals("https://8080-cs-123.cs-uk.cloudshell.dev/",
            HybridEndpoint.validated("https://8080-cs-123.cs-uk.cloudshell.dev/",
                HybridEndpoint.Engine.CLOUD))
    }

    @Test fun deniesPublicAndTokenBearingEndpoints() {
        listOf(
            "http://laptop.my-tailnet.ts.net",
            "https://evil.example.com",
            "https://laptop.my-tailnet.ts.net.evil.org",
            "https://owner:password@laptop.my-tailnet.ts.net",
            "https://laptop.my-tailnet.ts.net?api_key=abc",
            "https://laptop.my-tailnet.ts.net/#token",
            "https://laptop.my-tailnet.ts.net:443",
            "https://192.168.1.2:8765",
            "https://laptop.my-tailnet.ts.net/a",
            "https://laptop..ts.net",
            " https://laptop.my-tailnet.ts.net",
            "https://laptop.my-tailnet.ts.net\nevil.com"
        ).forEach { value ->
            try {
                HybridEndpoint.validated(value, HybridEndpoint.Engine.LAPTOP)
                throw AssertionError("Untrusted endpoint accepted: $value")
            } catch (_: IllegalArgumentException) { }
        }
    }

    @Test fun cloudMustMatchCloudShellPrivatePreview() {
        listOf("https://cloudshell.dev", "https://cs-123.cloudshell.dev",
               "https://8080-cs-1.cloudshell.dev.evil.net",
               "https://laptop.my-tailnet.ts.net",
               "http://8080-cs-1.cs-us.cloudshell.dev").forEach { value ->
            try {
                HybridEndpoint.validated(value, HybridEndpoint.Engine.CLOUD)
                throw AssertionError("Untrusted cloud endpoint accepted: $value")
            } catch (_: IllegalArgumentException) { }
        }
    }
}
