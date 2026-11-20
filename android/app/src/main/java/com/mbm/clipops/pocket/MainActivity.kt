package com.mbm.clipops.pocket

import android.app.Activity
import android.content.ActivityNotFoundException
import androidx.browser.customtabs.CustomTabsIntent
import android.content.ContentValues
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.ArrayAdapter
import android.text.InputType
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.Presentation
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.ProgressHolder
import androidx.media3.transformer.Transformer
import androidx.media3.ui.PlayerView
import java.io.File
import java.io.IOException
import java.util.Locale

@androidx.annotation.OptIn(UnstableApi::class)
class MainActivity : Activity() {
    private val ink = Color.rgb(239, 246, 250)
    private val muted = Color.rgb(154, 173, 192)
    private val accent = Color.rgb(184, 247, 111)
    private val panel = Color.rgb(21, 34, 48)
    private val background = Color.rgb(10, 17, 27)
    private val handler = Handler(Looper.getMainLooper())

    private lateinit var player: ExoPlayer
    private lateinit var preview: PlayerView
    private lateinit var laptopUrl: EditText
    private lateinit var cloudUrl: EditText
    private lateinit var startInput: EditText
    private lateinit var endInput: EditText
    private lateinit var format: Spinner
    private lateinit var status: TextView
    private lateinit var progress: ProgressBar
    private lateinit var choose: Button
    private lateinit var export: Button
    private lateinit var cancel: Button
    private lateinit var share: Button

    private var sourceUri: Uri? = null
    private var outputUri: Uri? = null
    private var durationMs: Long = 0
    private var transformer: Transformer? = null
    private var tempFile: File? = null
    private var busy = false
    private var previewEndMs: Long? = null
    private var destroyed = false

    private val ticker = object : Runnable {
        override fun run() {
            val stop = previewEndMs
            if (stop != null && player.isPlaying && player.currentPosition >= stop) {
                player.pause()
                previewEndMs = null
            }
            if (busy) {
                val current = transformer
                if (current != null) {
                    val holder = ProgressHolder()
                    if (current.getProgress(holder) == Transformer.PROGRESS_STATE_AVAILABLE) {
                        progress.progress = holder.progress
                        setStatus("Rendering locally: " + holder.progress + "% · keep the app open")
                    }
                }
            }
            if (!destroyed) handler.postDelayed(this, 300L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = background
        window.navigationBarColor = background
        player = ExoPlayer.Builder(this).build()
        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_READY && player.duration > 0 && durationMs == 0L) {
                    durationMs = player.duration
                    endInput.setText(formatSeconds(durationMs))
                    setStatus("Video ready · duration " + formatSeconds(durationMs) + " seconds")
                }
            }
        })
        renderInterface()
        handler.post(ticker)
    }

    private fun dp(value: Int): Int = (resources.displayMetrics.density * value).toInt()

    private fun rounded(color: Int): GradientDrawable = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(15).toFloat()
    }

    private fun title(text: String, size: Float, color: Int = ink, bold: Boolean = false): TextView {
        return TextView(this).apply {
            this.text = text
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(null, Typeface.BOLD)
            setPadding(0, dp(3), 0, dp(8))
        }
    }

    private fun button(text: String, highlighted: Boolean = false, action: () -> Unit): Button {
        return Button(this).apply {
            this.text = text
            isAllCaps = false
            setTextColor(if (highlighted) this@MainActivity.background else ink)
            textSize = 14f
            background = rounded(if (highlighted) accent else panel)
            val layout = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(48)
            )
            layout.setMargins(0, dp(6), 0, dp(6))
            layoutParams = layout
            setOnClickListener { action() }
        }
    }

    private fun renderInterface() {
        val scroller = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(this@MainActivity.background)
        }
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(40))
        }
        scroller.addView(body)
        setContentView(scroller)

        body.addView(title("CLIPOPS  /  STUDIO", 14f, accent, true))
        body.addView(title("Your full editing factory.", 27f, ink, true))
        body.addView(title("Same desktop Studio on your phone. Choose a private laptop or Cloud Shell engine.", 13f, muted))
        body.addView(title("01  /  Full Studio · private engines", 18f, ink, true))
        body.addView(title("LAPTOP · Tailscale Serve / HTTPS", 12f, muted))
        laptopUrl = endpointField("https://laptop.your-tailnet.ts.net",
            "studio_laptop_url")
        body.addView(laptopUrl)
        body.addView(button("Open FULL Studio on laptop", highlighted = true) {
            openFullStudio(laptopUrl, HybridEndpoint.Engine.LAPTOP, "studio_laptop_url")
        })
        body.addView(title("CLOUD · Google account-gated Cloud Shell preview", 12f, muted))
        cloudUrl = endpointField("https://8080-...cloudshell.dev",
            "studio_cloud_url")
        body.addView(cloudUrl)
        body.addView(button("Open FULL Studio in private cloud") {
            openFullStudio(cloudUrl, HybridEndpoint.Engine.CLOUD, "studio_cloud_url")
        })
        body.addView(button("Launch Google Cloud Shell setup") {
            try {
                CustomTabsIntent.Builder().setShowTitle(true).build()
                    .launchUrl(this, Uri.parse("https://shell.cloud.google.com/"))
            } catch (_: ActivityNotFoundException) {
                setStatus("Install a supported browser to open Google Cloud Shell.")
            }
        })
        body.addView(title(
            "These open the original full Studio UI and FFmpeg engine in your signed-in browser. " +
            "Projects stay on the chosen engine; switching does not sync footage or jobs.",
            12f, muted
        ))
        body.addView(title("02  /  Offline Pocket · emergency trim", 18f, ink, true))
        body.addView(title("No network or AI required. Trim up to 3 minutes on-device.", 12f, muted))

        choose = button("Choose a video from your phone") { pickVideo() }
        body.addView(choose)
        preview = PlayerView(this).apply {
            player = this@MainActivity.player
            useController = true
            setBackgroundColor(Color.BLACK)
        }
        body.addView(preview, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(228)
        ))
        body.addView(title("Offline  /  Cut your clip", 18f, ink, true))

        startInput = numericField("Start time (seconds)", "0")
        endInput = numericField("End time (seconds)", "0")
        body.addView(title("Start time · seconds", 12f, muted))
        body.addView(startInput)
        body.addView(title("End time · seconds", 12f, muted))
        body.addView(endInput)
        body.addView(button("Set START to current playhead") { startInput.setText(formatSeconds(player.currentPosition)) })
        body.addView(button("Set END to current playhead") { endInput.setText(formatSeconds(player.currentPosition)) })
        body.addView(button("Preview selected range") { previewSelection() })

        body.addView(title("Offline  /  Framing", 18f, ink, true))
        body.addView(title("Fit keeps all original content. No face tracking yet.", 12f, muted))
        format = Spinner(this)
        val formats = listOf("Original aspect", "Vertical 9:16 · fit", "Square 1:1 · fit")
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, formats)
        format.adapter = adapter
        body.addView(format, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(52)
        ))

        body.addView(title("Offline  /  Export", 18f, ink, true))
        export = button("Export MP4 to Gallery", highlighted = true) { exportClip() }
        body.addView(export)
        cancel = button("Cancel export") { cancelExport() }
        body.addView(cancel)
        share = button("Share saved clip") { shareClip() }
        body.addView(share)
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progress = 0
        }
        body.addView(progress)
        status = title("Select a video to start.", 13f, muted)
        status.gravity = Gravity.CENTER_HORIZONTAL
        body.addView(status)
        body.addView(title(
            "Offline Pocket does only trim and export. FULL Studio uses the same " +
            "desktop Python/FFmpeg engine over owner-authenticated private HTTPS. " +
            "No automatic cloud failover, cross-engine project sync or remote hosting is provisioned.",
            12f, muted
        ))
        cancel.isEnabled = false
        export.isEnabled = false
        share.isEnabled = false
    }

    private fun endpointField(hint: String, key: String): EditText {
        return EditText(this).apply {
            this.hint = hint
            setText(getPreferences(MODE_PRIVATE).getString(key, "") ?: "")
            setTextColor(ink)
            setHintTextColor(muted)
            textSize = 14f
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            background = rounded(panel)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(50)
            )
        }
    }

    private fun openFullStudio(input: EditText, engine: HybridEndpoint.Engine, key: String) {
        val url = try {
            HybridEndpoint.validated(input.text.toString(), engine)
        } catch (error: IllegalArgumentException) {
            setStatus(error.message ?: "A private HTTPS engine URL is required.")
            return
        }
        // Only clean HTTPS hostnames are persisted; NEVER passwords, cookies,
        // bearer tokens, signed URLs or transcripts.
        getPreferences(MODE_PRIVATE).edit().putString(key, url).apply()
        input.setText(url)
        try {
            CustomTabsIntent.Builder()
                .setShowTitle(true)
                .setToolbarColor(background)
                .build()
                .launchUrl(this, Uri.parse(url))
            setStatus("Opening full Studio. The chosen private engine must be running.")
        } catch (_: ActivityNotFoundException) {
            setStatus("Install Chrome or another browser before opening full Studio.")
        } catch (_: SecurityException) {
            setStatus("Your browser cannot open this private Studio URL.")
        }
    }

    private fun numericField(hint: String, value: String): EditText {
        return EditText(this).apply {
            this.hint = hint
            setText(value)
            setTextColor(ink)
            setHintTextColor(muted)
            textSize = 16f
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSelectAllOnFocus(true)
            background = rounded(panel)
            setPadding(dp(14), 0, dp(14), 0)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(50)
            )
        }
    }

    private fun formatSeconds(ms: Long): String =
        String.format(Locale.US, "%.2f", ms.coerceAtLeast(0) / 1000.0)

    private fun pickVideo() {
        if (busy) return
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "video/*"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        startActivityForResult(intent, REQUEST_VIDEO)
    }

    @Deprecated("Platform callback retained for simple standalone Android beta.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_VIDEO || resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // Some document providers permit read access only for this session.
        }
        try {
            val retriever = MediaMetadataRetriever()
            retriever.setDataSource(this, uri)
            durationMs = retriever.extractMetadata(
                MediaMetadataRetriever.METADATA_KEY_DURATION
            )?.toLongOrNull() ?: 0L
            retriever.release()
        } catch (_: Exception) {
            durationMs = 0L
        }
        sourceUri = uri
        outputUri = null
        share.isEnabled = false
        previewEndMs = null
        player.setMediaItem(MediaItem.fromUri(uri))
        player.prepare()
        startInput.setText("0")
        endInput.setText(formatSeconds(durationMs))
        export.isEnabled = true
        setStatus("Video selected. Set a clip range; exports are limited to 3 minutes.")
    }

    private fun selection(): Pair<Long, Long> {
        return ClipSelection.validate(
            startInput.text.toString().toDoubleOrNull(),
            endInput.text.toString().toDoubleOrNull(),
            durationMs
        )
    }

    private fun previewSelection() {
        if (busy || sourceUri == null) return
        try {
            val (start, end) = selection()
            player.seekTo(start)
            previewEndMs = end
            player.play()
            setStatus("Previewing original footage from " + formatSeconds(start) +
                " to " + formatSeconds(end) + " seconds.")
        } catch (error: IllegalArgumentException) {
            setStatus(error.message ?: "Invalid clip interval.")
        }
    }

    private fun exportClip() {
        val uri = sourceUri ?: return
        if (busy) return
        val bounds = try { selection() } catch (error: IllegalArgumentException) {
            setStatus(error.message ?: "Invalid clip interval.")
            return
        }
        val start = bounds.first
        val end = bounds.second
        previewEndMs = null
        player.pause()

        val source = MediaItem.Builder()
            .setUri(uri)
            .setClippingConfiguration(
                MediaItem.ClippingConfiguration.Builder()
                    .setStartPositionMs(start)
                    .setEndPositionMs(end)
                    .build()
            )
            .build()
        val edit = EditedMediaItem.Builder(source)
        when (format.selectedItemPosition) {
            1 -> edit.setEffects(Effects(emptyList(), listOf(
                Presentation.createForAspectRatio(9f / 16f, Presentation.LAYOUT_SCALE_TO_FIT)
            )))
            2 -> edit.setEffects(Effects(emptyList(), listOf(
                Presentation.createForAspectRatio(1f, Presentation.LAYOUT_SCALE_TO_FIT)
            )))
        }
        val target = File(cacheDir, "clipops-mobile-" + System.nanoTime() + ".mp4")
        tempFile = target
        busy = true
        choose.isEnabled = false
        export.isEnabled = false
        cancel.isEnabled = true
        progress.progress = 0
        setStatus("Export started. Keep ClipOps Pocket open.")
        try {
            transformer = Transformer.Builder(this)
                .setVideoMimeType(MimeTypes.VIDEO_H264)
                .setAudioMimeType(MimeTypes.AUDIO_AAC)
                .addListener(object : Transformer.Listener {
                    override fun onCompleted(composition: Composition, exportResult: ExportResult) {
                        publishOutput(target)
                    }

                    override fun onError(
                        composition: Composition,
                        exportResult: ExportResult,
                        exportException: ExportException
                    ) {
                        target.delete()
                        transformer = null
                        setBusy(false)
                        setStatus("Export failed: " + (
                            exportException.message ?: "Unsupported source codec or device encoder."
                        ))
                    }
                })
                .build()
            transformer?.start(edit.build(), target.absolutePath)
        } catch (error: Exception) {
            target.delete()
            transformer = null
            setBusy(false)
            setStatus("Unable to start export: " + (error.message ?: "Unknown issue"))
        }
    }

    private fun publishOutput(file: File) {
        transformer = null
        setStatus("Export complete. Saving MP4 to your Gallery...")
        Thread {
            val result = try {
                Result.success(saveToGallery(file))
            } catch (error: Exception) {
                Result.failure<Uri>(error)
            } finally {
                file.delete()
            }
            runOnUiThread {
                if (destroyed) return@runOnUiThread
                setBusy(false)
                result.onSuccess { saved ->
                    outputUri = saved
                    share.isEnabled = true
                    progress.progress = 100
                    setStatus("Saved to Gallery → Movies/ClipOps. Ready to share.")
                }.onFailure { error ->
                    setStatus("Export finished but could not save to Gallery: " +
                        (error.message ?: "Storage unavailable."))
                }
            }
        }.start()
    }

    private fun saveToGallery(file: File): Uri {
        if (!file.exists() || file.length() <= 0L) {
            throw IOException("The exported clip is missing or empty.")
        }
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "clipops-" +
                System.currentTimeMillis() + ".mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/ClipOps")
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val collection = MediaStore.Video.Media.getContentUri(
            MediaStore.VOLUME_EXTERNAL_PRIMARY
        )
        val uri = contentResolver.insert(collection, values)
            ?: throw IOException("Android MediaStore refused the export.")
        try {
            val output = contentResolver.openOutputStream(uri, "w")
                ?: throw IOException("Cannot write this video to the Gallery.")
            output.use { destination ->
                file.inputStream().use { source ->
                    source.copyTo(destination, 512 * 1024)
                }
            }
            contentResolver.update(uri, ContentValues().apply {
                put(MediaStore.Video.Media.IS_PENDING, 0)
            }, null, null)
            return uri
        } catch (error: Exception) {
            contentResolver.delete(uri, null, null)
            throw error
        }
    }

    private fun shareClip() {
        val uri = outputUri ?: return
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "video/mp4"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(intent, "Share ClipOps video"))
    }

    private fun cancelExport() {
        if (!busy) return
        try { transformer?.cancel() } catch (_: Exception) { }
        transformer = null
        tempFile?.delete()
        setBusy(false)
        setStatus("Export cancelled. Source video was not changed.")
    }

    private fun setBusy(value: Boolean) {
        busy = value
        choose.isEnabled = !value
        export.isEnabled = !value && sourceUri != null
        cancel.isEnabled = value
        share.isEnabled = !value && outputUri != null
    }

    private fun setStatus(message: String) {
        status.text = message
    }

    override fun onDestroy() {
        destroyed = true
        handler.removeCallbacks(ticker)
        if (busy) {
            try { transformer?.cancel() } catch (_: Exception) { }
            tempFile?.delete()
        }
        player.release()
        super.onDestroy()
    }

    companion object {
        private const val REQUEST_VIDEO = 51
    }
}
