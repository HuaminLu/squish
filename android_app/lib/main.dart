import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'engine.dart';
import 'plan.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Colors.black,
    systemNavigationBarIconBrightness: Brightness.light,
  ));
  runApp(const SquishApp());
}

const _white = Colors.white;
const _black = Colors.black;
const _grey = Color(0xFF9A9A9A); // MUTED
const _line = Color(0xFF3A3A3A); // FAINT
const _panel = Colors.black;
const _r = 12.0;
const _rs = 8.0;

class SquishApp extends StatelessWidget {
  const SquishApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Squish',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: _black,
        colorScheme: const ColorScheme.dark(
          primary: _white,
          onPrimary: _black,
          surface: _black,
          onSurface: _white,
          secondary: _white,
        ),
        textTheme: Typography.whiteMountainView.apply(fontFamily: 'Roboto'),
        splashFactory: InkSparkle.splashFactory,
      ),
      home: const Home(),
    );
  }
}

enum Phase { idle, picked, working, done, error }

class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with TickerProviderStateMixin {
  Phase phase = Phase.idle;
  String? uri, fileName, thumb;
  int fileSize = 0;
  SourceInfo? info;
  double preset = 10;
  bool custom = false;
  final customCtl = TextEditingController(text: '25');
  final customFocus = FocusNode();
  String? treeUri;
  String folderLabel = 'Downloads';
  Progress progress = const Progress('', 0, 0);
  SquishResult? result;
  String? error;
  late final AnimationController pulse =
      AnimationController(vsync: this, duration: const Duration(seconds: 2))
        ..repeat(reverse: true);

  @override
  void initState() {
    super.initState();
    _loadPrefs();
    customFocus.addListener(() {
      if (customFocus.hasFocus) setState(() => custom = true);
    });
  }

  @override
  void dispose() {
    pulse.dispose();
    customCtl.dispose();
    customFocus.dispose();
    super.dispose();
  }

  Future<void> _loadPrefs() async {
    final p = await SharedPreferences.getInstance();
    treeUri = p.getString('treeUri');
    folderLabel = await Engine.folderName(treeUri);
    final sp = p.getDouble('preset');
    final c = p.getBool('custom') ?? false;
    final cv = p.getString('customValue');
    if (mounted) {
      setState(() {
        if (sp != null) preset = sp;
        custom = c;
        if (cv != null) customCtl.text = cv;
      });
    }
  }

  Future<void> _savePrefs() async {
    final p = await SharedPreferences.getInstance();
    if (treeUri == null) {
      await p.remove('treeUri');
    } else {
      await p.setString('treeUri', treeUri!);
    }
    await p.setDouble('preset', preset);
    await p.setBool('custom', custom);
    await p.setString('customValue', customCtl.text);
  }

  double get targetMb {
    if (!custom) return preset;
    final v = double.tryParse(customCtl.text.trim()) ?? 0;
    return v;
  }

  bool get targetOk => targetMb >= 1 && targetMb <= 2000;

  Future<void> _pick() async {
    if (phase == Phase.working) return;
    HapticFeedback.selectionClick();
    final r = await Engine.pickVideo();
    if (r == null) return;
    setState(() {
      uri = r['uri'] as String;
      fileName = r['name'] as String;
      fileSize = (r['size'] as num).toInt();
      thumb = null;
      info = null;
      result = null;
      error = null;
      phase = Phase.picked;
    });
    try {
      final i = await Engine.probe(uri!);
      final t = await Engine.thumbnail(uri!, i.duration);
      if (!mounted) return;
      setState(() {
        info = i;
        thumb = t;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = 'Could not read that video.\n$e';
        phase = Phase.error;
      });
    }
  }

  Future<void> _pickFolder() async {
    if (phase == Phase.working) return;
    HapticFeedback.selectionClick();
    final r = await Engine.pickFolder();
    if (r == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        backgroundColor: _white,
        content: Text(
            'Downloads is already the default. Android blocks picking the root Downloads folder, so pick a subfolder (e.g. Download/Squish) if you want one.',
            style: TextStyle(color: _black, fontWeight: FontWeight.w600)),
        duration: Duration(seconds: 5),
      ));
      return;
    }
    setState(() {
      treeUri = r['uri'] as String;
      folderLabel = r['name'] as String;
    });
    _savePrefs();
  }

  void _resetFolder() {
    setState(() {
      treeUri = null;
      folderLabel = 'Downloads';
    });
    _savePrefs();
  }

  Future<void> _go() async {
    if (phase == Phase.working) {
      await Engine.cancel();
      return;
    }
    if (uri == null || info == null || !targetOk) return;
    FocusScope.of(context).unfocus();
    HapticFeedback.mediumImpact();
    _savePrefs();
    setState(() {
      phase = Phase.working;
      progress = const Progress('Starting', 0, 0);
      error = null;
      result = null;
    });
    final base = (fileName ?? 'video').replaceAll(RegExp(r'\.[^.]+$'), '');
    try {
      final r = await Engine.squish(
        uri: uri!,
        baseName: base,
        src: info!,
        targetMb: targetMb,
        treeUri: treeUri,
        onProgress: (p) {
          if (mounted) setState(() => progress = p);
        },
      );
      if (!mounted) return;
      HapticFeedback.heavyImpact();
      setState(() {
        result = r;
        phase = Phase.done;
      });
    } on Cancelled {
      if (mounted) setState(() => phase = Phase.picked);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = '$e';
        phase = Phase.error;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final working = phase == Phase.working;
    final canGo = uri != null && info != null && targetOk && !working;
    return Scaffold(
      resizeToAvoidBottomInset: false,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _header(),
              const SizedBox(height: 10),
              Expanded(child: _sourceCard()),
              const SizedBox(height: 12),
              _caps('Size limit'),
              _presets(),
              const SizedBox(height: 12),
              _caps('Save to'),
              _folderRow(),
              const SizedBox(height: 12),
              _bigButton(canGo, working),
            ],
          ),
        ),
      ),
    );
  }

  Widget _header() {
    return Container(
      padding: const EdgeInsets.only(bottom: 6),
      decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: _line, width: 1))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Image.asset('assets/icon.png', width: 30, height: 30),
          const SizedBox(width: 8),
          const Text('squish',
              style: TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1.5,
                  height: 1)),
          const SizedBox(width: 8),
          const Padding(
            padding: EdgeInsets.only(bottom: 5),
            child: Text('simple video compressor',
                style: TextStyle(
                    fontSize: 13,
                    fontStyle: FontStyle.italic,
                    fontWeight: FontWeight.w600,
                    color: _grey,
                    height: 1)),
          ),
        ],
      ),
    );
  }

  Widget _caps(String t) => Padding(
        padding: const EdgeInsets.only(left: 2, bottom: 6),
        child: Text(t.toUpperCase(),
            style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.3,
                color: _grey)),
      );

  // ---------- source / progress card ----------
  Widget _sourceCard() {
    return GestureDetector(
      onTap: _pick,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOutCubic,
        decoration: BoxDecoration(
          color: _panel,
          borderRadius: BorderRadius.circular(_r),
          border: Border.all(color: _white, width: 1.5),
        ),
        clipBehavior: Clip.antiAlias,
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 350),
          switchInCurve: Curves.easeOutCubic,
          child: switch (phase) {
            Phase.idle => _emptyCard(),
            Phase.picked => _pickedCard(),
            Phase.working => _workingCard(),
            Phase.done => _doneCard(),
            Phase.error => _errorCard(),
          },
        ),
      ),
    );
  }

  Widget _emptyCard() {
    return Center(
      key: const ValueKey('empty'),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ScaleTransition(
            scale: Tween(begin: 0.96, end: 1.04).animate(
                CurvedAnimation(parent: pulse, curve: Curves.easeInOut)),
            child: _roundIcon(Icons.video_file_outlined, 92, 44),
          ),
          const SizedBox(height: 18),
          const Text('Tap to choose a video',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text('Any size · any format',
              style: TextStyle(color: _grey, fontSize: 15)),
        ],
      ),
    );
  }

  Widget _thumbBackdrop() {
    if (thumb == null) {
      return Container(color: _panel);
    }
    return Image.file(File(thumb!), fit: BoxFit.cover,
        frameBuilder: (c, child, frame, sync) => AnimatedOpacity(
            opacity: frame == null ? 0 : 1,
            duration: const Duration(milliseconds: 300),
            child: child));
  }

  Widget _scrim() => Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0x55000000), Color(0x22000000), Color(0xDD000000)],
          ),
        ),
      );

  Widget _pickedCard() {
    final i = info;
    final meta = i == null
        ? 'Reading…'
        : '${i.width}×${i.height} · ${_fmtDur(i.duration)} · ${fmtMb(fileSize)}';
    return Stack(
      key: const ValueKey('picked'),
      fit: StackFit.expand,
      children: [
        _thumbBackdrop(),
        _scrim(),
        Positioned(
          left: 18,
          right: 18,
          bottom: 16,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(fileName ?? '',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 19, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(meta, style: TextStyle(color: _grey, fontSize: 14)),
            ],
          ),
        ),
        Positioned(
          top: 12,
          right: 12,
          child: _roundIcon(Icons.swap_horiz_rounded, 44, 22, filled: true),
        ),
      ],
    );
  }

  Widget _workingCard() {
    final pct = (progress.fraction * 100).clamp(0, 100).floor();
    return Stack(
      key: const ValueKey('working'),
      fit: StackFit.expand,
      children: [
        _thumbBackdrop(),
        Container(color: Colors.black.withValues(alpha: 0.72)),
        Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 150,
                height: 150,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    TweenAnimationBuilder<double>(
                      tween: Tween(end: progress.fraction),
                      duration: const Duration(milliseconds: 500),
                      curve: Curves.easeOut,
                      builder: (c, v, _) => CircularProgressIndicator(
                        value: v <= 0.005 ? null : v,
                        strokeWidth: 8,
                        strokeCap: StrokeCap.round,
                        color: _white,
                        backgroundColor: _white.withValues(alpha: 0.15),
                      ),
                    ),
                    Center(
                      child: Text('$pct%',
                          style: const TextStyle(
                              fontSize: 40,
                              fontWeight: FontWeight.w900,
                              letterSpacing: -1)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),
              Text(progress.stage,
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(
                  progress.speed > 0
                      ? '${progress.speed.toStringAsFixed(1)}× realtime · under ${_fmtTarget()}'
                      : 'under ${_fmtTarget()}',
                  style: TextStyle(color: _grey, fontSize: 14)),
            ],
          ),
        ),
        Positioned(
          left: 18,
          right: 18,
          bottom: 16,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: TweenAnimationBuilder<double>(
              tween: Tween(end: progress.fraction),
              duration: const Duration(milliseconds: 500),
              builder: (c, v, _) => LinearProgressIndicator(
                value: v <= 0.005 ? null : v,
                minHeight: 8,
                color: _white,
                backgroundColor: _white.withValues(alpha: 0.15),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _doneCard() {
    final r = result!;
    final p = r.plan;
    final ratio = fileSize > 0 ? fileSize / r.bytes : 0;
    final detail = [
      if (p.outHeight > 0) '${p.outHeight}p' else 'same size',
      '${p.videoKbps} kbps',
      '${r.elapsed.inSeconds}s',
      if (ratio > 1) '${ratio.toStringAsFixed(1)}× smaller',
    ].join(' · ');
    return Stack(
      key: const ValueKey('done'),
      fit: StackFit.expand,
      children: [
        _thumbBackdrop(),
        _scrim(),
        Center(
          child: TweenAnimationBuilder<double>(
            tween: Tween(begin: 0.6, end: 1),
            duration: const Duration(milliseconds: 500),
            curve: Curves.elasticOut,
            builder: (c, v, child) => Transform.scale(scale: v, child: child),
            child: _roundIcon(Icons.check_rounded, 96, 56, filled: true),
          ),
        ),
        Positioned(
          left: 18,
          right: 18,
          bottom: 16,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(fmtMb(r.bytes),
                        style: const TextStyle(
                            fontSize: 30,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -1)),
                    Text('${r.savedName}\nsaved to ${r.savedWhere}',
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 14)),
                    const SizedBox(height: 2),
                    Text(detail, style: TextStyle(color: _grey, fontSize: 12)),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              GestureDetector(
                onTap: () => Engine.share(r.shareUri),
                child: _roundIcon(Icons.ios_share_rounded, 56, 26, filled: true),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _errorCard() {
    return Center(
      key: const ValueKey('error'),
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _roundIcon(Icons.priority_high_rounded, 72, 36, filled: true),
            const SizedBox(height: 14),
            const Text('Something went wrong',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(error ?? '',
                textAlign: TextAlign.center,
                maxLines: 5,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: _grey, fontSize: 13)),
            const SizedBox(height: 8),
            Text('Tap to pick another video',
                style: TextStyle(color: _grey, fontSize: 13)),
          ],
        ),
      ),
    );
  }

  // ---------- presets ----------
  Widget _presets() {
    final sizes = [5.0, 8.0, 10.0, 20.0];
    return Column(
      children: [
        Row(
          children: [
            for (var k = 0; k < sizes.length; k++) ...[
              if (k > 0) const SizedBox(width: 10),
              Expanded(child: _tile(sizes[k])),
            ],
          ],
        ),
        const SizedBox(height: 10),
        _customTile(),
      ],
    );
  }

  Widget _tile(double mb) {
    final sel = !custom && preset == mb;
    return GestureDetector(
      onTap: () {
        if (phase == Phase.working) return;
        HapticFeedback.selectionClick();
        customFocus.unfocus();
        setState(() {
          custom = false;
          preset = mb;
        });
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        height: 68,
        decoration: BoxDecoration(
          color: sel ? _white : _black,
          borderRadius: BorderRadius.circular(_rs),
          border: Border.all(color: sel ? _white : _line, width: sel ? 1.5 : 1),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('${mb.round()}',
                style: TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    height: 1,
                    color: sel ? _black : _white)),
            const SizedBox(height: 3),
            Text('MB',
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                    color: sel ? _black : _grey)),
          ],
        ),
      ),
    );
  }

  Widget _customTile() {
    final sel = custom;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
      height: 56,
      decoration: BoxDecoration(
        color: sel ? _white : _black,
        borderRadius: BorderRadius.circular(_rs),
        border: Border.all(color: sel ? _white : _line, width: sel ? 1.5 : 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(_rs),
        onTap: () {
          if (phase == Phase.working) return;
          setState(() => custom = true);
          customFocus.requestFocus();
        },
        child: Row(
          children: [
            const SizedBox(width: 18),
            AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              width: 26,
              height: 26,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: sel ? _black : Colors.transparent,
                border: Border.all(color: sel ? _black : _grey, width: 2),
              ),
              child: sel
                  ? const Icon(Icons.check_rounded, size: 18, color: _white)
                  : null,
            ),
            const SizedBox(width: 14),
            Text('Custom',
                style: TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w700,
                    color: sel ? _black : _white)),
            const Spacer(),
            SizedBox(
              width: 84,
              child: TextField(
                controller: customCtl,
                focusNode: customFocus,
                enabled: phase != Phase.working,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                textAlign: TextAlign.right,
                onChanged: (_) => setState(() => custom = true),
                onSubmitted: (_) => customFocus.unfocus(),
                style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
                    color: sel ? _black : _white),
                cursorColor: sel ? _black : _white,
                decoration: const InputDecoration(
                  isDense: true,
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ),
            const SizedBox(width: 6),
            Text('MB',
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                    color: sel ? _black : _grey)),
            const SizedBox(width: 18),
          ],
        ),
      ),
    );
  }

  // ---------- folder ----------
  Widget _folderRow() {
    return Container(
      height: 54,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(_rs),
        border: Border.all(color: _line, width: 1),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(_rs),
          onTap: _pickFolder,
          child: Row(
            children: [
              const SizedBox(width: 14),
              _roundIcon(Icons.folder_rounded, 34, 19, filled: true),
              const SizedBox(width: 12),
              Text('Save to', style: TextStyle(color: _grey, fontSize: 15)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(folderLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 17, fontWeight: FontWeight.w700)),
              ),
              if (treeUri != null)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: GestureDetector(
                    onTap: _resetFolder,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 7),
                      decoration: BoxDecoration(
                        color: _white,
                        borderRadius: BorderRadius.circular(_rs),
                      ),
                      child: const Text('Use Downloads',
                          style: TextStyle(
                              color: _black,
                              fontSize: 13,
                              fontWeight: FontWeight.w800)),
                    ),
                  ),
                )
              else
                const Padding(
                  padding: EdgeInsets.only(right: 12),
                  child: Icon(Icons.chevron_right_rounded, color: _grey),
                ),
            ],
          ),
        ),
      ),
    );
  }

  // ---------- big button ----------
  Widget _bigButton(bool canGo, bool working) {
    final label = working
        ? 'Cancel'
        : phase == Phase.done
            ? 'Squish It again'
            : targetOk
                ? 'Squish It to ${_fmtTarget()}'
                : 'Squish It';
    final enabled = canGo || working;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 250),
      opacity: enabled ? 1 : 0.35,
      child: SizedBox(
        height: 56,
        child: Material(
          color: working ? _black : _white,
          borderRadius: BorderRadius.circular(_r),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: enabled ? _go : null,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(_r),
                border: Border.all(color: _white, width: 1.5),
              ),
              alignment: Alignment.center,
              child: Text(label,
                  style: TextStyle(
                      fontSize: 19,
                      fontWeight: FontWeight.w800,
                      color: working ? _white : _black)),
            ),
          ),
        ),
      ),
    );
  }

  Widget _roundIcon(IconData icon, double size, double iconSize,
      {bool filled = false}) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: filled ? _white : Colors.transparent,
        border: filled ? null : Border.all(color: _white, width: 2.5),
      ),
      child: Icon(icon, size: iconSize, color: filled ? _black : _white),
    );
  }

  String _fmtTarget() {
    final t = targetMb;
    return '${t == t.roundToDouble() ? t.round() : t} MB';
  }

  String _fmtDur(double s) {
    final d = Duration(milliseconds: (s * 1000).round());
    final m = d.inMinutes, sec = d.inSeconds % 60;
    return m > 0 ? '$m:${sec.toString().padLeft(2, '0')}' : '${sec}s';
  }
}
