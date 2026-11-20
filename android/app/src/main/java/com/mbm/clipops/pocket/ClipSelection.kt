package com.mbm.clipops.pocket

import kotlin.math.roundToLong

/** Strict source-relative bounds; no action outside the selected original file. */
internal object ClipSelection {
    private const val MAX_CLIP_MS = 180_000L

    fun validate(startSeconds: Double?, endSeconds: Double?, durationMs: Long): Pair<Long, Long> {
        require(startSeconds != null && endSeconds != null &&
            startSeconds.isFinite() && endSeconds.isFinite()) {
            "Enter valid start and end times in seconds."
        }
        require(startSeconds >= 0.0 && endSeconds > startSeconds) {
            "End must be later than start."
        }
        require(durationMs > 0L) { "Wait for the source video duration to load." }
        val start = (startSeconds * 1000.0).roundToLong()
        val end = (endSeconds * 1000.0).roundToLong()
        require(end > start && end - start >= 250L) {
            "Select at least 0.25 seconds of video."
        }
        require(end <= durationMs + 100L) {
            "The selection cannot extend beyond the original footage."
        }
        require(end - start <= MAX_CLIP_MS) {
            "Phone beta exports clips up to three minutes."
        }
        return start to minOf(end, durationMs)
    }
}
