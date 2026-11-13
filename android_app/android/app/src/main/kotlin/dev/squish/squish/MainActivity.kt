package dev.squish.squish

import android.Manifest
import android.app.Activity
import android.content.ContentUris
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.util.Size
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private val channelName = "squish/files"
    private val reqVideo = 4101
    private val reqFolder = 4102
    private val reqPerm = 4103
    private var pending: MethodChannel.Result? = null
    private var pendingPerm: MethodChannel.Result? = null
    private val pool = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    private val mediaPermission: String
        get() = if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_VIDEO
                else Manifest.permission.READ_EXTERNAL_STORAGE

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName).setMethodCallHandler { call, result ->
            when (call.method) {
                "pickVideo" -> {
                    pending = result
                    val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "video/*"
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    startActivityForResult(i, reqVideo)
                }
                "pickFolder" -> {
                    pending = result
                    val i = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or
                                Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                    }
                    startActivityForResult(i, reqFolder)
                }
                "folderName" -> {
                    val uri = Uri.parse(call.argument<String>("uri")!!)
                    result.success(treeDisplayName(uri))
                }
                "saveFile" -> {
                    try {
                        val src = File(call.argument<String>("src")!!)
                        val name = call.argument<String>("name")!!
                        val tree = call.argument<String?>("treeUri")
                        result.success(saveFile(src, name, tree?.let { Uri.parse(it) }))
                    } catch (e: Exception) {
                        result.error("save", e.message, null)
                    }
                }
                "shareFile" -> {
                    val uri = Uri.parse(call.argument<String>("uri")!!)
                    val i = Intent(Intent.ACTION_SEND).apply {
                        type = "video/mp4"
                        putExtra(Intent.EXTRA_STREAM, uri)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    startActivity(Intent.createChooser(i, "Share video"))
                    result.success(null)
                }
                "hasMediaPermission" -> result.success(hasMediaPermission())
                "requestMediaPermission" -> {
                    if (hasMediaPermission()) { result.success(true); return@setMethodCallHandler }
                    pendingPerm = result
                    ActivityCompat.requestPermissions(this, arrayOf(mediaPermission), reqPerm)
                }
                "listRecentVideos" -> {
                    val limit = call.argument<Int>("limit") ?: 24
                    pool.execute {
                        val list = try { listRecentVideos(limit) } catch (e: Exception) { emptyList<Map<String, Any>>() }
                        main.post { result.success(list) }
                    }
                }
                "videoThumb" -> {
                    val uri = Uri.parse(call.argument<String>("uri")!!)
                    pool.execute {
                        val p = try { videoThumb(uri) } catch (e: Exception) { null }
                        main.post { result.success(p) }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun hasMediaPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, mediaPermission) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == reqPerm) {
            val ok = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
            pendingPerm?.success(ok)
            pendingPerm = null
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val r = pending ?: return
        pending = null
        if (resultCode != Activity.RESULT_OK || data?.data == null) {
            r.success(null); return
        }
        val uri = data.data!!
        when (requestCode) {
            reqVideo -> {
                var name = "video"
                var size = 0L
                contentResolver.query(uri, null, null, null, null)?.use { c ->
                    if (c.moveToFirst()) {
                        val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                        val si = c.getColumnIndex(OpenableColumns.SIZE)
                        if (ni >= 0) name = c.getString(ni) ?: name
                        if (si >= 0 && !c.isNull(si)) size = c.getLong(si)
                    }
                }
                r.success(mapOf("uri" to uri.toString(), "name" to name, "size" to size))
            }
            reqFolder -> {
                contentResolver.takePersistableUriPermission(
                    uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                r.success(mapOf("uri" to uri.toString(), "name" to treeDisplayName(uri)))
            }
        }
    }

    /** Newest videos in the device gallery (MediaStore). */
    private fun listRecentVideos(limit: Int): List<Map<String, Any>> {
        if (!hasMediaPermission()) return emptyList()
        val coll = MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        val proj = arrayOf(MediaStore.Video.Media._ID, MediaStore.Video.Media.DISPLAY_NAME,
            MediaStore.Video.Media.SIZE, MediaStore.Video.Media.DATE_MODIFIED)
        val out = ArrayList<Map<String, Any>>()
        val cursor = if (Build.VERSION.SDK_INT >= 30) {
            val args = Bundle().apply {
                putStringArray(android.content.ContentResolver.QUERY_ARG_SORT_COLUMNS, arrayOf(MediaStore.Video.Media.DATE_MODIFIED))
                putInt(android.content.ContentResolver.QUERY_ARG_SORT_DIRECTION, android.content.ContentResolver.QUERY_SORT_DIRECTION_DESCENDING)
                putInt(android.content.ContentResolver.QUERY_ARG_LIMIT, limit)
            }
            contentResolver.query(coll, proj, args, null)
        } else {
            @Suppress("DEPRECATION")
            contentResolver.query(coll, proj, null, null, "${MediaStore.Video.Media.DATE_MODIFIED} DESC LIMIT $limit")
        }
        cursor?.use { c ->
            val idI = c.getColumnIndexOrThrow(MediaStore.Video.Media._ID)
            val nI = c.getColumnIndexOrThrow(MediaStore.Video.Media.DISPLAY_NAME)
            val sI = c.getColumnIndexOrThrow(MediaStore.Video.Media.SIZE)
            val dI = c.getColumnIndexOrThrow(MediaStore.Video.Media.DATE_MODIFIED)
            while (c.moveToNext() && out.size < limit) {
                val id = c.getLong(idI)
                out.add(mapOf(
                    "uri" to ContentUris.withAppendedId(coll, id).toString(),
                    "name" to (c.getString(nI) ?: "video"),
                    "size" to c.getLong(sI),
                    "date" to c.getLong(dI) * 1000L))
            }
        }
        return out
    }

    /** Small gallery thumbnail, cached in the app cache dir. */
    private fun videoThumb(uri: Uri): String? {
        val dir = File(cacheDir, "gthumbs").apply { mkdirs() }
        val f = File(dir, uri.toString().hashCode().toUInt().toString() + ".jpg")
        if (f.exists()) return f.absolutePath
        val bmp: Bitmap? = if (Build.VERSION.SDK_INT >= 29) {
            contentResolver.loadThumbnail(uri, Size(320, 180), null)
        } else {
            @Suppress("DEPRECATION")
            MediaStore.Video.Thumbnails.getThumbnail(contentResolver, ContentUris.parseId(uri),
                MediaStore.Video.Thumbnails.MINI_KIND, null)
        }
        if (bmp == null) return null
        FileOutputStream(f).use { bmp.compress(Bitmap.CompressFormat.JPEG, 80, it) }
        return f.absolutePath
    }

    private fun treeDisplayName(tree: Uri): String {
        val id = try { DocumentsContract.getTreeDocumentId(tree) } catch (e: Exception) { return "Folder" }
        // "primary:Movies/Clips" -> "Movies/Clips"; "primary:" -> "Internal storage"
        val path = id.substringAfter(':', id)
        if (path.isEmpty()) return if (id.startsWith("primary")) "Internal storage" else id
        return path
    }

    /** Copies [src] into the SAF tree or, when null, into public Downloads. */
    private fun saveFile(src: File, name: String, tree: Uri?): Map<String, Any> {
        if (tree != null) {
            val parent = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
            val doc = DocumentsContract.createDocument(contentResolver, parent, "video/mp4", name)
                ?: throw IllegalStateException("Could not create file in folder")
            contentResolver.openOutputStream(doc)!!.use { out -> src.inputStream().use { it.copyTo(out) } }
            var finalName = name
            contentResolver.query(doc, arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME), null, null, null)?.use {
                if (it.moveToFirst()) finalName = it.getString(0) ?: name
            }
            return mapOf("name" to finalName, "where" to treeDisplayName(tree), "uri" to doc.toString())
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, "video/mp4")
                put(MediaStore.MediaColumns.RELATIVE_PATH, "Download")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val coll = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            val item = contentResolver.insert(coll, values) ?: throw IllegalStateException("Could not create file in Downloads")
            contentResolver.openOutputStream(item)!!.use { out -> src.inputStream().use { it.copyTo(out) } }
            values.clear(); values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            contentResolver.update(item, values, null, null)
            var finalName = name
            contentResolver.query(item, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)?.use {
                if (it.moveToFirst()) finalName = it.getString(0) ?: name
            }
            return mapOf("name" to finalName, "where" to "Downloads", "uri" to item.toString())
        }
        @Suppress("DEPRECATION")
        val dir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
        dir.mkdirs()
        var dst = File(dir, name)
        var n = 1
        while (dst.exists()) { dst = File(dir, name.removeSuffix(".mp4") + " (${n++}).mp4") }
        src.copyTo(dst, overwrite = false)
        val uri = FileProvider.getUriForFile(this, "$packageName.files", dst)
        return mapOf("name" to dst.name, "where" to "Downloads", "uri" to uri.toString())
    }
}
