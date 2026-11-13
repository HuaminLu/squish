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

class Plan {
  final int limitBytes;
  final int videoKbps;
  final int audioKbps; // 0 = no audio
  final bool audioCopy;
  final bool mono;
  final int outHeight; // 0 = keep source size
  final double outFps; // 0 = keep source fps
  const Plan({
    required this.limitBytes,
    required this.videoKbps,
    required this.audioKbps,
    required this.audioCopy,
    required this.mono,
    required this.outHeight,
    required this.outFps,
  });

  Plan withVideoKbps(int v) => Plan(
        limitBytes: limitBytes,
        videoKbps: v,
        audioKbps: audioKbps,
        audioCopy: audioCopy,
        mono: mono,
        outHeight: outHeight,
        outFps: outFps,
      );
}

const double kHeadroom = 0.975; // aim 2.5 % under the limit
const double kMinBitsPerPixel = 0.035;
const List<int> kLadder = [2160, 1440, 1080, 720, 540, 480, 360, 240];

Plan makePlan(SourceInfo src, double targetMb) {
  final limitBytes = (targetMb * 1000000).floor();
  final totalKbps = limitBytes * 8 * kHeadroom / src.duration / 1000.0;

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
    if (src.audioCodec == 'aac' &&
        src.audioKbps > 0 &&
        src.audioKbps <= audioKbps + 8) {
      audioCopy = true;
      audioKbps = src.audioKbps;
    }
  }

  // ~1 % for the MP4 container (moov, chunk tables, etc.).
  int videoKbps = (totalKbps * 0.99 - audioKbps).floor();
  if (videoKbps < 40) videoKbps = 40;

  // Frame rate: never above 60; drop to 30 when bits are scarce.
  double fps = src.fps;
  double outFps = 0;
  if (fps > 60) {
    outFps = 60;
    fps = 60;
  }

  // Resolution ladder from the bits-per-pixel budget.
  final srcH = src.height;
  final srcW = src.width;
  int outHeight = 0; // keep
  int chosen = srcH;
  final rungs = [srcH, ...kLadder.where((h) => h < srcH)];
  for (final h in rungs) {
    final w = srcW * h / srcH;
    final bpp = videoKbps * 1000.0 / (w * h * fps);
    if (bpp >= kMinBitsPerPixel) {
      chosen = h;
      break;
    }
    chosen = h; // smallest rung if nothing qualifies
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
  );
}

String fmtMb(int bytes) => '${(bytes / 1000000).toStringAsFixed(1)} MB';
