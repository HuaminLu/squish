import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit_config.dart';
import 'package:ffmpeg_kit_flutter_new/ffprobe_kit.dart';
import 'package:ffmpeg_kit_flutter_new/return_code.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'plan.dart';

class Progress {
  final String stage;
  final double fraction; // 0..1 overall
  final double speed; // encode speed vs realtime
  const Progress(this.stage, this.fraction, this.speed);
}

class SquishResult {
  final String savedName;
  final String savedWhere;
  final String shareUri;
  final int bytes;
  final Plan plan;
  final Duration elapsed;
  const SquishResult(this.savedName, this.savedWhere, this.shareUri, this.bytes,
      this.plan, this.elapsed);
}

class Engine {
  static const _ch = MethodChannel('squish/files');
  static bool _cancelled = false;

  static Future<Map<String, dynamic>?> pickVideo() async {
    final r = await _ch.invokeMethod<Map>('pickVideo');
    return r?.cast<String, dynamic>();
  }

  static Future<Map<String, dynamic>?> pickFolder() async {
    final r = await _ch.invokeMethod<Map>('pickFolder');
    return r?.cast<String, dynamic>();
  }

  static Future<String> folderName(String? treeUri) async {
    if (treeUri == null) return 'Downloads';
    return await _ch.invokeMethod<String>('folderName', {'uri': treeUri}) ??
        'Folder';
  }

  static Future<void> share(String uri) =>
      _ch.invokeMethod('shareFile', {'uri': uri});

  static Future<void> cancel() async {
    _cancelled = true;
    await FFmpegKit.cancel();
  }

  static Future<String> _safRead(String uri) async =>
      (await FFmpegKitConfig.getSafParameterForRead(uri))!;

  static Future<SourceInfo> probe(String uri) async {
    final saf = await _safRead(uri);
    final s = await FFprobeKit.execute(
        '-v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,bit_rate,channels:format=duration -of json "$saf"');
    final out = await s.getOutput() ?? '{}';
    final j = jsonDecode(out) as Map<String, dynamic>;
    final streams = (j['streams'] as List? ?? []).cast<Map<String, dynamic>>();
    final fmt = (j['format'] as Map<String, dynamic>? ?? {});
    final v = streams.firstWhere((e) => e['codec_type'] == 'video',
        orElse: () => throw Exception('No video stream found'));
    final a = streams.cast<Map<String, dynamic>?>().firstWhere(
        (e) => e!['codec_type'] == 'audio',
        orElse: () => null);
    double fps = _ratio(v['avg_frame_rate']) ?? _ratio(v['r_frame_rate']) ?? 30;
    if (fps <= 0 || fps > 240) fps = 30;
    final duration = double.tryParse('${fmt['duration']}') ?? 0;
    if (duration <= 0) throw Exception('Could not read video duration');
    return SourceInfo(
      duration: duration,
      width: (v['width'] as num).toInt(),
      height: (v['height'] as num).toInt(),
      fps: fps,
      hasAudio: a != null,
      audioCodec: a?['codec_name']?.toString() ?? '',
      audioKbps: ((int.tryParse('${a?['bit_rate']}') ?? 0) / 1000).round(),
      audioChannels: (a?['channels'] as num?)?.toInt() ?? 2,
    );
  }

  static double? _ratio(dynamic s) {
    if (s == null) return null;
    final p = s.toString().split('/');
    if (p.length != 2) return double.tryParse(s.toString());
    final n = double.tryParse(p[0]) ?? 0, d = double.tryParse(p[1]) ?? 0;
    if (d == 0) return null;
    return n / d;
  }

  /// Preview frame at [at] seconds, optionally centre-cropped like the output.
  static Future<String?> thumbnail(String uri, double at,
      {String crop = '', int srcW = 0, int srcH = 0, int height = 540}) async {
    final dir = await getTemporaryDirectory();
    final out = '${dir.path}/thumb_${DateTime.now().millisecondsSinceEpoch}.jpg';
    final vf = <String>[];
    final cr = (crop.isNotEmpty && srcW > 0) ? cropRect(srcW, srcH, crop) : null;
    if (cr != null) vf.add('crop=${cr.$1}:${cr.$2}:${cr.$3}:${cr.$4}');
    vf.add('scale=-2:$height');
    final saf = await _safRead(uri);
    final s = await FFmpegKit.execute(
        '-y -v error -ss ${at.clamp(0, 1e9).toStringAsFixed(2)} -i "$saf" -frames:v 1 -vf ${vf.join(',')} -q:v 4 "$out"');
    if (ReturnCode.isSuccess(await s.getReturnCode()) && File(out).existsSync()) {
      return out;
    }
    return null;
  }

  /// Full pipeline: 2-pass x264, verify size, retry pass 2 if over, save.
  static Future<SquishResult> squish({
    required String uri,
    required String baseName,
    required SourceInfo src,
    required double targetMb,
    required String? treeUri,
    required void Function(Progress) onProgress,
    Edit? edit,
  }) async {
    _cancelled = false;
    edit ??= Edit();
    final sw = Stopwatch()..start();
    final dir = await getTemporaryDirectory();
    final tag = DateTime.now().millisecondsSinceEpoch;
    final log = '${dir.path}/pl_$tag';
    final outPath = '${dir.path}/out_$tag.mp4';
    var plan = makePlan(src, targetMb, edit);

    // -ss/-t as INPUT options: they bound what is read, so speed changes do
    // not pull extra source.
    final (s, e) = edit.span(src.duration);
    final inArgs = (s > 0.05 ? '-ss ${s.toStringAsFixed(3)} ' : '') +
        (edit.trimmed(src.duration) ? '-t ${(e - s).toStringAsFixed(3)} ' : '');
    final vf = videoFilters(src, edit, plan);
    final vfArg = vf.isEmpty ? '' : '-vf ${vf.join(',')} ';
    final af = audioFilters(edit);
    final afArg = af.isEmpty ? '' : '-af ${af.join(',')} ';

    // Phones: "veryfast" keeps the encode near real-time; still 2-pass so
    // the size lands where we aim and quality is spread evenly.
    const preset = 'veryfast';
    String common(Plan p) =>
        '$vfArg-pix_fmt yuv420p -fps_mode cfr -c:v libx264 -preset $preset -profile:v high '
        '-b:v ${p.videoKbps}k -maxrate ${(p.videoKbps * 1.5).round()}k -bufsize ${p.videoKbps * 3}k '
        '-passlogfile "$log"';

    String audio(Plan p) {
      if (p.audioKbps == 0) return '-an';
      if (p.audioCopy) return '-c:a copy';
      return '$afArg-c:a aac -b:a ${p.audioKbps}k ${p.mono ? '-ac 1' : ''}';
    }

    final outDur = plan.outDuration;
    Future<void> run(String cmd, String stage, double from, double to) async {
      final c = Completer<void>();
      final session = await FFmpegKit.executeAsync(
        cmd,
        (s) async => c.complete(),
        null,
        (st) {
          final t = st.getTime() / 1000.0;
          final f = (t / outDur).clamp(0.0, 1.0);
          onProgress(Progress(stage, from + (to - from) * f, st.getSpeed()));
        },
      );
      await c.future;
      final rc = await session.getReturnCode();
      if (_cancelled || ReturnCode.isCancel(rc)) throw const Cancelled();
      if (!ReturnCode.isSuccess(rc)) {
        final logs = await session.getAllLogsAsString();
        throw Exception('ffmpeg failed:\n${_tail(logs ?? '')}');
      }
    }

    // Pass 1 (analysis only, no audio, no output).
    var saf = await _safRead(uri);
    await run('-y $inArgs-i "$saf" ${common(plan)} -pass 1 -an -f null /dev/null',
        'Analyzing', 0.0, 0.45);

    // Pass 2, verify, and shrink the bitrate if the file still came out over.
    int bytes = 0;
    for (var attempt = 0; attempt < 3; attempt++) {
      saf = await _safRead(uri);
      await run(
          '-y $inArgs-i "$saf" ${common(plan)} -pass 2 ${audio(plan)} -movflags +faststart "$outPath"',
          attempt == 0 ? 'Encoding' : 'Tightening',
          0.45,
          0.98);
      bytes = File(outPath).lengthSync();
      if (bytes < plan.limitBytes) break;
      final ratio = plan.limitBytes * 0.96 / bytes;
      plan = plan.withVideoKbps((plan.videoKbps * ratio).floor());
    }
    if (bytes >= plan.limitBytes) {
      throw Exception('Could not get under the limit. Try a bigger size.');
    }

    onProgress(Progress('Saving', 0.99, 0));
    final sizeTag = targetMb == targetMb.roundToDouble()
        ? '${targetMb.round()}mb'
        : '${targetMb}mb';
    final name = '$baseName-$sizeTag${edit.tag(src.duration)}.mp4';
    final saved = (await _ch.invokeMethod<Map>('saveFile', {
      'src': outPath,
      'name': name,
      'treeUri': treeUri,
    }))!
        .cast<String, dynamic>();
    try {
      File(outPath).deleteSync();
      for (final f in Directory(dir.path).listSync()) {
        if (f.path.contains('pl_$tag')) f.deleteSync();
      }
    } catch (_) {}
    sw.stop();
    return SquishResult(saved['name'] as String, saved['where'] as String,
        saved['uri'] as String, bytes, plan, sw.elapsed);
  }

  static String _tail(String s) {
    final lines = s.trim().split('\n');
    return lines.sublist(lines.length > 6 ? lines.length - 6 : 0).join('\n');
  }
}

class Cancelled implements Exception {
  const Cancelled();
}
