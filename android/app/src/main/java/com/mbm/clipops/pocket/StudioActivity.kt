package com.mbm.clipops.pocket

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.DownloadListener
import android.webkit.SslErrorHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.io.ByteArrayInputStream
import java.net.URI
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** Complete desktop Studio browser client; FFmpeg and private projects remain on the chosen server. */
class StudioActivity : Activity() {
    private val backgroundColor=Color.rgb(10,17,27)
    private val surface=Color.rgb(23,36,51)
    private val ink=Color.rgb(239,246,250)
    private val muted=Color.rgb(155,173,192)
    private val accent=Color.rgb(184,247,111)
    private lateinit var container: FrameLayout
    private lateinit var home: ScrollView
    private lateinit var workspace: LinearLayout
    private lateinit var browser: WebView
    private lateinit var laptop: EditText
    private lateinit var cloud: EditText
    private lateinit var code: EditText
    private lateinit var status: TextView
    private val preferences by lazy {getSharedPreferences("hybrid_studio",MODE_PRIVATE)}
    private var engine: StudioEndpoint?=null
    private var fileCallback:ValueCallback<Array<Uri>>?=null
    private var download: Download?=null
    private var fullScreen:View?=null
    private var fullScreenExit:WebChromeClient.CustomViewCallback?=null
    private var closing=false

    private data class Download(val url:String,val name:String,val mime:String)
    private fun dp(value:Int)=(resources.displayMetrics.density*value).toInt()
    private fun shape(color:Int):GradientDrawable=GradientDrawable().apply {
        setColor(color);cornerRadius=dp(14).toFloat()
    }
    private fun text(value:String,size:Float=14f,color:Int=ink,bold:Boolean=false)=
        TextView(this).apply {
            this.text=value;textSize=size;setTextColor(color)
            if(bold)setTypeface(null,Typeface.BOLD)
            setPadding(0,dp(6),0,dp(8))
        }
    private fun field(hintText:String,value:String="",password:Boolean=false)=EditText(this).apply {
        hint=hintText;setText(value);setSingleLine(true)
        setTextColor(ink);setHintTextColor(muted);textSize=14f
        background=shape(surface);setPadding(dp(12),0,dp(12),0)
        inputType=if(password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        layoutParams=LinearLayout.LayoutParams(-1,dp(51))
    }
    private fun button(label:String,primary:Boolean=false,act:()->Unit)=Button(this).apply {
        text=label;textSize=14f;isAllCaps=false
        background=shape(if(primary)accent else surface)
        setTextColor(if(primary)backgroundColor else ink)
        setOnClickListener{act()}
        layoutParams=LinearLayout.LayoutParams(-1,dp(48)).apply{
            setMargins(0,dp(6),0,dp(6))
        }
    }

    override fun onCreate(savedInstanceState:Bundle?){
        super.onCreate(savedInstanceState)
        window.statusBarColor=backgroundColor
        window.navigationBarColor=backgroundColor
        container=FrameLayout(this).apply{setBackgroundColor(backgroundColor)}
        setContentView(container)
        createHome()
        createWorkspace()
        showHome()
    }
    private fun createHome(){
        home=ScrollView(this).apply{isFillViewport=true}
        val body=LinearLayout(this).apply{
            orientation=LinearLayout.VERTICAL
            setPadding(dp(20),dp(26),dp(20),dp(36))
        }
        home.addView(body)
        container.addView(home,FrameLayout.LayoutParams(-1,-1))
        body.addView(text("CLIPOPS  /  FULL STUDIO",14f,accent,true))
        body.addView(text("Your editing factory.\nOn Android.",27f,ink,true))
        body.addView(text("The same projects, source moments, transcripts, captions, rendering presets and approved exports as the desktop Studio.",14f,muted))
        body.addView(text("LAPTOP PROCESSOR",13f,accent,true))
        laptop=field("https://laptop.yourtailnet.ts.net",preferences.getString("laptop","").orEmpty())
        body.addView(laptop)
        body.addView(button("Connect to laptop",true){connect(laptop.text.toString(),"laptop")})
        body.addView(text("CLOUD PROCESSOR",13f,accent,true))
        cloud=field("https://cloud.yourtailnet.ts.net",preferences.getString("cloud","").orEmpty())
        body.addView(cloud)
        body.addView(button("Connect to cloud"){connect(cloud.text.toString(),"cloud")})
        body.addView(text("ONE-TIME PRIVATE PAIRING CODE",13f,accent,true))
        body.addView(text("On a Tailscale backend, enter the 16-character code shown in that server's console. Never share this code with a third party.",12f,muted))
        code=field("Code from your own computer",password=true)
        body.addView(code)
        body.addView(text("Switch processing engines explicitly. Laptop and cloud have separate project libraries unless you arrange private synchronization.",12f,muted))
        body.addView(button("Offline quick-trim Pocket mode"){
            startActivity(Intent(this,MainActivity::class.java))
        })
        body.addView(button("Open Cloud Shell in Chrome"){
            startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://shell.cloud.google.com/")))
        })
        status=text("No cloud deployment or paid service is configured.",12f,muted)
        status.gravity=Gravity.CENTER_HORIZONTAL
        body.addView(status)
    }

    private fun createWorkspace(){
        workspace=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;visibility=View.GONE}
        val nav=LinearLayout(this).apply{
            orientation=LinearLayout.HORIZONTAL
            setBackgroundColor(surface)
        }
        fun navButton(name:String,click:()->Unit)=Button(this).apply{
            text=name;textSize=12f;isAllCaps=false;setTextColor(ink)
            setOnClickListener{click()}
        }
        nav.addView(navButton("Engines"){showHome()},LinearLayout.LayoutParams(0,dp(48),1f))
        nav.addView(navButton("Reload"){browser.reload()},LinearLayout.LayoutParams(0,dp(48),1f))
        nav.addView(navButton("Back"){if(browser.canGoBack())browser.goBack() else showHome()},LinearLayout.LayoutParams(0,dp(48),1f))
        workspace.addView(nav)
        browser=WebView(this)
        browser.setBackgroundColor(backgroundColor)
        browser.settings.apply {
            javaScriptEnabled=true
            domStorageEnabled=true
            allowFileAccess=false
            allowContentAccess=true // User-selected Android SAF content URIs.
            allowFileAccessFromFileURLs=false
            allowUniversalAccessFromFileURLs=false
            mixedContentMode=WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically=false
            setSupportMultipleWindows(false)
            safeBrowsingEnabled=true
            mediaPlaybackRequiresUserGesture=true
        }
        CookieManager.getInstance().setAcceptCookie(true)
        browser.webViewClient=object:WebViewClient(){
            override fun shouldOverrideUrlLoading(v:WebView,req:WebResourceRequest):Boolean{
                if(engine?.permits(req.url.toString())==true)return false
                if(req.isForMainFrame&&req.hasGesture()&&req.url.scheme=="https"){
                    try{startActivity(Intent(Intent.ACTION_VIEW,req.url))}catch(_:Exception){}
                }
                return true
            }
            override fun shouldInterceptRequest(v:WebView,req:WebResourceRequest):WebResourceResponse?{
                if(req.url.scheme in listOf("http","https")&&engine?.permits(req.url.toString())!=true){
                    return WebResourceResponse("text/plain","UTF-8",ByteArrayInputStream(ByteArray(0)))
                }
                return null
            }
            override fun onReceivedError(v:WebView,req:WebResourceRequest,err:WebResourceError){
                if(req.isForMainFrame)runOnUiThread{message("Private Studio unavailable. Check the engine and your tailnet connection.")}
            }
            @Suppress("DEPRECATION")
            override fun onReceivedSslError(v:WebView,handler:SslErrorHandler,error:SslError){
                handler.cancel()
                message("TLS certificate rejected. Do not bypass certificate verification.")
            }
        }
        browser.webChromeClient=object:WebChromeClient(){
            override fun onShowFileChooser(v:WebView,callback:ValueCallback<Array<Uri>>,params:FileChooserParams):Boolean{
                fileCallback?.onReceiveValue(null)
                fileCallback=callback
                val mime=if(params.acceptTypes.any{it.startsWith("video/")})"video/*" else "*/*"
                val intent=Intent(Intent.ACTION_OPEN_DOCUMENT).apply{
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type=mime
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE,params.mode==FileChooserParams.MODE_OPEN_MULTIPLE)
                }
                try{startActivityForResult(intent,REQUEST_FILE)}
                catch(_:Exception){fileCallback=null;callback.onReceiveValue(null);message("File chooser unavailable.")}
                return true
            }
            override fun onShowCustomView(view:View,callback:CustomViewCallback){
                fullScreen=view;fullScreenExit=callback
                container.addView(view,FrameLayout.LayoutParams(-1,-1))
            }
            override fun onHideCustomView(){
                fullScreen?.let{container.removeView(it)}
                fullScreen=null;fullScreenExit=null
            }
        }
        browser.setDownloadListener(DownloadListener{url,_,disposition,_,length->
            requestDownload(url,disposition,length)
        })
        workspace.addView(browser,LinearLayout.LayoutParams(-1,0,1f))
        container.addView(workspace,FrameLayout.LayoutParams(-1,-1))
    }

    private fun connect(raw:String,kind:String){
        val selected=try{StudioEndpoint.parse(raw)}catch(error:IllegalArgumentException){
            message(error.message?:"Invalid private endpoint");return
        }
        preferences.edit().putString(kind,selected.origin).apply()
        val pairing=code.text.toString().trim()
        code.text.clear() // Never persist codes in Android preferences.
        if(selected.type==StudioEndpoint.Type.CLOUD_SHELL || pairing.isEmpty()){
            open(selected) // Existing valid cookie or browser pairing form may be used.
            return
        }
        if(pairing.length!=16||pairing.any{it !in "0123456789abcdef"}){
            message("Pairing code must contain exactly 16 lowercase hexadecimal characters.")
            return
        }
        message("Connecting to private processing engine...")
        Thread{
            val cookie=try{
                val conn=URL(selected.origin+"/api/remote-pair")
                    .openConnection() as HttpsURLConnection
                try{
                    conn.connectTimeout=15000
                    conn.readTimeout=15000
                    conn.instanceFollowRedirects=false
                    conn.requestMethod="POST"
                    conn.setRequestProperty("Content-Type","application/json")
                    conn.doOutput=true
                    conn.outputStream.use{out->
                        out.write(("{\"code\":\""+pairing+"\"}").toByteArray(Charsets.UTF_8))
                    }
                    if(conn.responseCode!=204)throw IllegalStateException("Pairing rejected (HTTP "+conn.responseCode+"). Check server console code.")
                    conn.getHeaderField("Set-Cookie")
                        ?:throw IllegalStateException("No secure session returned.")
                }finally{conn.disconnect()}
            }catch(error:Exception){
                runOnUiThread{message(error.message?:"Private pairing failed.")}
                return@Thread
            }
            runOnUiThread{
                CookieManager.getInstance().setCookie(selected.origin,cookie){success->
                    if(success){CookieManager.getInstance().flush();open(selected)}
                    else message("Could not save HTTPS session cookie.")
                }
            }
        }.start()
    }
    private fun open(selected:StudioEndpoint){
        engine=selected
        home.visibility=View.GONE
        workspace.visibility=View.VISIBLE
        browser.loadUrl(selected.origin+"/")
    }
    private fun showHome(){
        fullScreenExit?.onCustomViewHidden()
        engine=null
        if(::browser.isInitialized)browser.loadUrl("about:blank")
        workspace.visibility=View.GONE
        home.visibility=View.VISIBLE
    }

    private fun requestDownload(url:String,disposition:String,length:Long){
        val selected=engine?:return
        val target=try{URI(url)}catch(_:Exception){message("Invalid export link");return}
        if(!selected.permits(url)||target.rawQuery!=null||target.rawFragment!=null){
            message("Blocked external download.");return
        }
        val path=target.path.orEmpty()
        val good=Regex("/media/[a-f0-9]{32}/c[0-9]{2,4}/(export|srt|vtt)").matches(path)
            ||Regex("/api/projects/[a-f0-9]{32}/approved-delivery\\.zip").matches(path)
        if(!good||length>8L*1024*1024*1024){
            message("Only approved Studio exports may be saved.");return
        }
        val extension=when{
            path.endsWith(".zip")->".zip"
            path.endsWith("/srt")->".srt"
            path.endsWith("/vtt")->".vtt"
            else->".mp4"
        }
        val proposed=disposition.substringAfter("filename=\"","").substringBefore("\"","")
        val rawName=proposed.ifEmpty{"clipops-"+System.currentTimeMillis()+extension}
        val safeName=rawName.replace(Regex("[^A-Za-z0-9._-]"),"_").take(96)
        val mime=when(extension){
            ".zip"->"application/zip"
            ".srt"->"application/x-subrip"
            ".vtt"->"text/vtt"
            else->"video/mp4"
        }
        download=Download(url,safeName,mime)
        try{
            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply{
                addCategory(Intent.CATEGORY_OPENABLE)
                type=mime
                putExtra(Intent.EXTRA_TITLE,safeName)
                addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            },REQUEST_SAVE)
        }catch(_:Exception){download=null;message("Android Save As unavailable.")}
    }

    @Deprecated("Legacy document-picker callback for this standalone Activity")
    override fun onActivityResult(requestCode:Int,resultCode:Int,data:Intent?){
        super.onActivityResult(requestCode,resultCode,data)
        if(requestCode==REQUEST_FILE){
            val callback=fileCallback
            fileCallback=null
            val uris=mutableListOf<Uri>()
            if(resultCode==RESULT_OK){
                data?.data?.let{uris.add(it)}
                data?.clipData?.let{clip->
                    for(index in 0 until clip.itemCount.coerceAtMost(8)){
                        clip.getItemAt(index).uri?.let{if(!uris.contains(it))uris.add(it)}
                    }
                }
            }
            callback?.onReceiveValue(uris.filter{it.scheme=="content"}.takeIf{it.isNotEmpty()}?.toTypedArray())
        }
        if(requestCode==REQUEST_SAVE){
            val ticket=download
            download=null
            val uri=data?.data
            if(resultCode==RESULT_OK&&ticket!=null&&uri?.scheme=="content")
                saveApproved(ticket,uri)
        }
    }

    private fun saveApproved(ticket:Download,destination:Uri){
        val selected=engine?:return
        val cookie=CookieManager.getInstance().getCookie(selected.origin)
        if(cookie.isNullOrBlank()){message("Session expired. Pair again.");return}
        message("Saving approved Studio export to Android...")
        Thread{
            try{
                val conn=URL(ticket.url).openConnection() as HttpsURLConnection
                try{
                    conn.connectTimeout=15000;conn.readTimeout=60000
                    conn.instanceFollowRedirects=false
                    conn.setRequestProperty("Cookie",cookie)
                    if(conn.responseCode!=200)throw IllegalStateException("Export denied (HTTP "+conn.responseCode+").")
                    if(conn.contentLengthLong>8L*1024*1024*1024)throw IllegalStateException("Export too large.")
                    val output=contentResolver.openOutputStream(destination,"w")
                        ?:throw IllegalStateException("Cannot open selected destination.")
                    output.use{dest->
                        conn.inputStream.use{input->
                            val buffer=ByteArray(256*1024)
                            var total=0L
                            while(true){
                                val n=input.read(buffer)
                                if(n<0)break
                                total+=n
                                if(total>8L*1024*1024*1024)throw IllegalStateException("Export too large.")
                                dest.write(buffer,0,n)
                            }
                            if(total==0L)throw IllegalStateException("Downloaded file was empty.")
                        }
                    }
                }finally{conn.disconnect()}
                runOnUiThread{message("Saved "+ticket.name)}
            }catch(error:Exception){
                try{contentResolver.delete(destination,null,null)}catch(_:Exception){}
                runOnUiThread{message(error.message?:"Download failed.")}
            }
        }.start()
    }
    private fun message(value:String){
        if(closing)return
        android.widget.Toast.makeText(this,value,android.widget.Toast.LENGTH_LONG).show()
        if(::home.isInitialized&&home.visibility==View.VISIBLE)status.text=value
    }

    @Deprecated("Platform back navigation")
    override fun onBackPressed(){
        if(fullScreen!=null){fullScreenExit?.onCustomViewHidden();return}
        if(workspace.visibility==View.VISIBLE){
            if(browser.canGoBack())browser.goBack() else showHome()
        }else super.onBackPressed()
    }
    override fun onDestroy(){
        closing=true
        fileCallback?.onReceiveValue(null)
        browser.stopLoading()
        browser.destroy()
        super.onDestroy()
    }
    companion object{
        private const val REQUEST_FILE=601
        private const val REQUEST_SAVE=602
    }
}
