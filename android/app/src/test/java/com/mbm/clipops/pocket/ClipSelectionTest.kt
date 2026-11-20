package com.mbm.clipops.pocket

import org.junit.Assert.assertEquals
import org.junit.Test

class ClipSelectionTest {
    @Test fun normalSelection() {
        assertEquals(1500L to 12000L, ClipSelection.validate(1.5, 12.0, 30000))
    }

    @Test fun rejectsBoundaryAndInvalidValues() {
        listOf(
            -1.0 to 5.0,
            5.0 to 2.0,
            0.0 to 0.1,
            0.0 to 20.2,
            Double.NaN to 2.0,
            Double.POSITIVE_INFINITY to 2.0,
            1.0 to Double.NEGATIVE_INFINITY
        ).forEach { (start, end) ->
            try {
                ClipSelection.validate(start, end, 20000)
                throw AssertionError("Rejected input should not be allowed.")
            } catch (_: IllegalArgumentException) {
                // Expected.
            }
        }
    }

    @Test fun rejectsOversizedClip() {
        try {
            ClipSelection.validate(0.0, 181.0, 300_000)
            throw AssertionError("Oversized selection must be rejected.")
        } catch (_: IllegalArgumentException) {
            // Expected.
        }
    }

    @Test fun rejectMissingDuration() {
        try {
            ClipSelection.validate(0.0, 10.0, 0)
            throw AssertionError("No duration must fail.")
        } catch (_: IllegalArgumentException) {
            // Expected.
        }
    }
}
