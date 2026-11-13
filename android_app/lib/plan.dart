/// Compression planning. Mirrors squish_core.py on the desktop side exactly.
///
/// Rules:
///  * "N MB" means N * 1,000,000 bytes (decimal), the stricter reading, so a
///    20 MB result is always below 20.0 MB however the receiver counts it.
///  * We aim a few percent under the limit to absorb container overhead and
///    rate-control drift, then verify the real file and re-encode if needed.
///  * Resolution is chosen from the bits-per-pixel budget: the largest ladder
///    rung that still gets enough bits per pixel (what 8mb.video does by hand:
///    1080p source at 1233 kbps -> 720p).
///  * Optional edits: speed (0.25x-4x), trim (start/end), centre crop.
class SourceInfo {
  final double duration; // seconds
  final int width;
  final int height;
  final double fps;
  final bool hasAudio;
  final String audioCodec;
  final int audioKbps;
  final int audioChannels;
  const SourceInfo({
    required this.duration,
    required this.width,
    required this.height,
    required this.fps,
    required this.hasAudio,
    this.audioCodec = '',
    this.audioKbps = 0,
    this.audioChannels = 2,
  });
}

const List<double> kSpeeds = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0];
const List<String> kCrops = ['', '16:9', '1:1', '9:16', '4:3'];

class Edit {
  double speed = 1.0; // 0.25 .. 4
  double start = 0.0; // seconds
  double end = 0.0; // seconds, 0 = until the end
  String crop = ''; // '', '16:9', '1:1', '9:16', '4:3'

  (double, double) span(double duration) {
    var s = start.clamp(0.0, duration);
    var e = end > 0 ? end : duration;
    e = duration > 0.5 ? e.clamp(s + 0.5, duration) : duration;
    return (s, e);
  }

  bool trimmed(double duration) {
    final (s, e) = span(duration);
    return s > 0.05 || e < duration - 0.05;
  }

  bool get speedChanged => (speed - 1).abs() > 1e-6;

  double outDuration(double duration) {
    final (s, e) = span(duration);
    return ((e - s) / speed).clamp(0.1, double.infinity);
  }

  String tag(double duration) {
    final parts = <String>[];
    if (speedChanged) parts.add("${g(speed)}x");
    if (trimmed(duration)) parts.add('cut');
    if (crop.isNotEmpty) parts.add(crop.replaceAll(':', 'x'));
    return parts.map((p) => '-$p').join();
  }

  static String g(double v) =>
      v == v.roundToDouble() ? '${v.round()}' : v.toString();
}

/// Centre crop (w, h, x, y) to a 'W:H' aspect, even dimensions; null = no crop.
(int, int, int, int)? cropRect(int w, int h, String aspect) {
  if (aspect.isEmpty) return null;
  final p = aspect.split(':');
  final a = double.parse(p[0]) / double.parse(p[1]);
  int cw, ch;
  if (w / h > a) {
    ch = h;
    cw = (h * a).round();
  } else {
    cw = w;
    ch = (w / a).round();
  }
  cw -= cw % 2;
  ch -= ch % 2;
  if (cw >= w && ch >= h) return null;
  return (cw, ch, (w - cw) ~/ 2, (h - ch) ~/ 2);
}

class Plan {
  final int limitBytes;
  final int videoKbps;
  final int audioKbps; // 0 = no audio
  final bool audioCopy;
  final bool mono;
  final int outHeight; // 0 = keep source size
  final double outFps; // 0 = keep source fps
  final double outDuration;
  final int cropW;
  final int cropH;
  const Plan({
    required this.limitBytes,
    required this.videoKbps,
    required this.audioKbps,
    required this.audioCopy,
    required this.mono,
    required this.outHeight,
    required this.outFps,
    required this.outDuration,
    this.cropW = 0,
    this.cropH = 0,
  });

  Plan withVideoKbps(int v) => Plan(
        limitBytes: limitBytes,
        videoKbps: v,
        audioKbps: audioKbps,
        audioCopy: audioCopy,
        mono: mono,
        outHeight: outHeight,
        outFps: outFps,
        outDuration: outDuration,
        cropW: cropW,
        cropH: cropH,
      );
}

const double kHeadroom = 0.975; // aim 2.5 % under the limit
const double kMinBitsPerPixel = 0.035;
const int kMaxVideoKbps = 30000;
const List<int> kLadder = [2160, 1440, 1080, 720, 540, 480, 360, 240];

Plan makePlan(SourceInfo src, double targetMb, [Edit? edit]) {
  edit ??= Edit();
  final outDuration = edit.outDuration(src.duration);
  final cr = cropRect(src.width, src.height, edit.crop);
  final srcW = cr?.$1 ?? src.width;
  final srcH = cr?.$2 ?? src.height;

  final limitBytes = (targetMb * 1000000).floor();
  final totalKbps = limitBytes * 8 * kHeadroom / outDuration / 1000.0;

  // Audio budget scales with the total budget.
  int audioKbps = 0;
  bool mono = false;
  bool audioCopy = false;
  if (src.hasAudio) {
    if (totalKbps >= 1400) {
      audioKbps = 128;
    } else if (totalKbps >= 800) {
      audioKbps = 96;
    } else if (totalKbps >= 400) {
      audioKbps = 64;
    } else {
      audioKbps = 48;
      mono = true;
    }
    if (src.audioChannels <= 1) mono = true;
    // Copying is lossless and instant when the source is already AAC and
    // not bigger than the budget we would have spent anyway.
    if (!edit.speedChanged &&
        src.audioCodec == 'aac' &&
        src.audioKbps > 0 &&
        src.audioKbps <= audioKbps + 8) {
      audioCopy = true;
      audioKbps = src.audioKbps;
    }
  }

  // ~1 % for the MP4 container (moov, chunk tables, etc.).
  int videoKbps = (totalKbps * 0.99 - audioKbps).floor();
  videoKbps = videoKbps.clamp(40, kMaxVideoKbps);

  // Frame rate: never above 60; drop to 30 when bits are scarce.
  double fps = src.fps;
  double outFps = 0;
  if (fps > 60) {
    outFps = 60;
    fps = 60;
  }

  // Resolution ladder from the bits-per-pixel budget.
  int outHeight = 0; // keep
  int chosen = srcH;
  final rungs = [srcH, ...kLadder.where((h) => h < srcH)];
  for (final h in rungs) {
    final w = srcW * h / srcH;
    final bpp = videoKbps * 1000.0 / (w * h * fps);
    chosen = h;
    if (bpp >= kMinBitsPerPixel) break;
  }
  if (chosen != srcH) outHeight = chosen;

  // If even the smallest rung is starved and fps > 30, drop to 30.
  if (fps > 30) {
    final w = srcW * chosen / srcH;
    final bpp = videoKbps * 1000.0 / (w * chosen * fps);
    if (bpp < kMinBitsPerPixel) outFps = 30;
  }

  return Plan(
    limitBytes: limitBytes,
    videoKbps: videoKbps,
    audioKbps: audioKbps,
    audioCopy: audioCopy,
    mono: mono,
    outHeight: outHeight,
    outFps: outFps,
    outDuration: outDuration,
    cropW: cr?.$1 ?? 0,
    cropH: cr?.$2 ?? 0,
  );
}

List<String> videoFilters(SourceInfo src, Edit edit, Plan plan) {
  final vf = <String>[];
  final cr = cropRect(src.width, src.height, edit.crop);
  if (cr != null) vf.add('crop=${cr.$1}:${cr.$2}:${cr.$3}:${cr.$4}');
  if (edit.speedChanged) vf.add('setpts=PTS/${edit.speed}');
  if (plan.outHeight > 0) vf.add('scale=-2:${plan.outHeight}');
  if (plan.outFps > 0) vf.add('fps=${plan.outFps}');
  return vf;
}

List<String> audioFilters(Edit edit) {
  var f = edit.speed;
  if (!edit.speedChanged) return [];
  final chain = <String>[];
  while (f > 2.0) {
    chain.add('atempo=2.0');
    f /= 2.0;
  }
  while (f < 0.5) {
    chain.add('atempo=0.5');
    f *= 2.0;
  }
  chain.add('atempo=$f');
  return chain;
}

String fmtMb(int bytes) => '${(bytes / 1000000).toStringAsFixed(1)} MB';

String fmtTime(double s) {
  final t = s.round().clamp(0, 1 << 30);
  return '${t ~/ 60}:${(t % 60).toString().padLeft(2, '0')}';
}
