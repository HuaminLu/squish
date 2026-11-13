package dev.squish.squish

import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    private val channelName = "squish/files"
    private val reqVideo = 4101
    private val reqFolder = 4102
    private var pending: MethodChannel.Result? = null

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
                else -> result.notImplemented()
            }
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
