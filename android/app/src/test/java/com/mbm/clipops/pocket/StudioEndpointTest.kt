package com.mbm.clipops.pocket

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StudioEndpointTest {
    @Test fun privateLaptopAndCloudEndpoint() {
        val laptop = StudioEndpoint.parse("https://desktop.myteam.ts.net")
        val cloud = StudioEndpoint.parse("https://cloud.myteam.ts.net/")
        assertEquals(StudioEndpoint.Type.TAILNET, laptop.type)
        assertEquals(StudioEndpoint.Type.TAILNET, cloud.type)
        assertEquals("https://cloud.myteam.ts.net", cloud.origin)
        assertTrue(laptop.permits("https://desktop.myteam.ts.net/api/projects"))
        assertTrue(laptop.permits("https://desktop.myteam.ts.net/media/abc"))
        assertFalse(laptop.permits("https://desktop.myteam.ts.net.evil.example"))
        assertFalse(laptop.permits("https://cloud.myteam.ts.net"))
        assertFalse(laptop.permits("http://desktop.myteam.ts.net"))
        assertFalse(laptop.permits("https://desktop.myteam.ts.net:8443"))
    }

    @Test fun restrictedCloudShellPreview() {
        val endpoint=StudioEndpoint.parse("https://8080-cs-xyz-default.cs-us-east1-vpcf.cloudshell.dev")
        assertEquals(StudioEndpoint.Type.CLOUD_SHELL, endpoint.type)
        assertFalse(endpoint.permits("https://accounts.google.com/signin"))
    }

    @Test fun rejectsPublicRoutesSecretsAndSpoofedHosts() {
        val bad = listOf(
            "http://desktop.myteam.ts.net",
            "https://desktop.myteam.ts.net:8443",
            "https://desktop.myteam.ts.net/account",
            "https://desktop.myteam.ts.net?key=x",
            "https://desktop.myteam.ts.net#secret",
            "https://user@desktop.myteam.ts.net",
            "https://desktop.myteam.ts.net.evil.example",
            "https://myteam.ts.net",
            "https://example.com",
            "https://8081-cs-xyz.example.cloudshell.dev",
            "https://8080-cs-xyz.cloudshell.dev.evil.example",
            "https://127.0.0.1",
            "http://localhost:8765",
            "https://desktop..ts.net",
            "https://DESKTOP.myteam.ts.net",
            "javascript:alert(1)"
        )
        for (value in bad) {
            try {
                StudioEndpoint.parse(value)
                throw AssertionError("Bad backend accepted: $value")
            } catch (_: IllegalArgumentException) {
                // expected
            }
        }
    }
}
