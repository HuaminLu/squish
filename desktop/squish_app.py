"""Squish - shrink a video under a size limit, fully offline. Flet desktop UI."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time

import flet as ft

import squish_core as core

WHITE, BLACK, GREY, LINE, PANEL = "#FFFFFF", "#000000", "#9A9A9A", "#3A3A3A", "#000000"
HOVER = "#1AFFFFFF"
R, RS = 12, 8
VERSION = "1.0"
PRESETS = [5, 8, 10, 20]


def settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Squish")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d: dict):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def downloads_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def fmt_dur(s: float) -> str:
    s = int(s)
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else f"{s}s"


async def main(page: ft.Page):
    page.title = "Squish"
    page.bgcolor = BLACK
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    w = page.window
    w.width, w.height = 400, 470
    w.resizable = False
    w.maximizable = False
    w.title_bar_hidden = True
    w.bgcolor = BLACK
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    ico = os.path.join(base, "icon.ico")
    if os.path.exists(ico):
        w.icon = ico
    ico = os.path.join(base, "icon.png")
    page.theme = page.dark_theme = ft.Theme(
        font_family="Segoe UI",
        color_scheme=ft.ColorScheme(primary=WHITE, on_primary=BLACK, surface=BLACK, on_surface=WHITE, outline=WHITE),
    )

    st = load_settings()
    state = {
        "src": None, "info": None, "thumb": None,
        "preset": float(st.get("preset", 10)), "custom": bool(st.get("custom", False)),
        "out_dir": st.get("out_dir") or downloads_dir(),
        "phase": "idle", "job": None, "result": None, "error": None,
        "progress": core.Progress("", 0.0, 0.0),
    }

    picker = ft.FilePicker()
    page.services.append(picker)

    def persist():
        save_settings({"preset": state["preset"], "custom": state["custom"],
                       "custom_value": custom_field.value, "out_dir": state["out_dir"]})

    def target_mb() -> float:
        if not state["custom"]:
            return state["preset"]
        try:
            return float((custom_field.value or "").strip())
        except ValueError:
            return 0.0

    def target_ok() -> bool:
        return 1 <= target_mb() <= 2000

    def fmt_target() -> str:
        t = target_mb()
        return f"{int(t) if t.is_integer() else t} MB"

    def round_icon(icon, size, isize, filled=False):
        return ft.Container(
            width=size, height=size, shape=ft.BoxShape.CIRCLE,
            bgcolor=WHITE if filled else None,
            border=None if filled else ft.Border.all(2.5, WHITE),
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(icon, size=isize, color=BLACK if filled else WHITE),
        )

    # ---------------- source card ----------------
    card_body = ft.Container(expand=True, alignment=ft.Alignment.CENTER)
    card = ft.Container(
        expand=True, bgcolor=PANEL, border_radius=R, border=ft.Border.all(1.5, WHITE),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS, content=card_body, ink=True,
        animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT_CUBIC),
    )

    thumb_ctl = {"img": None, "bytes": None}

    def thumb_image():
        # One Image control per thumbnail, reused across re-renders so it is not reloaded every progress tick.
        if state["thumb"]:
            if thumb_ctl["bytes"] is not state["thumb"]:
                thumb_ctl["bytes"] = state["thumb"]
                thumb_ctl["img"] = ft.Image(src=state["thumb"], fit=ft.BoxFit.COVER, expand=True,
                                            fade_in_animation=ft.Animation(300))
            return thumb_ctl["img"]
        return ft.Container(bgcolor=PANEL, expand=True)

    def scrim(alpha: float = 0.0):
        return ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                colors=["#55000000", f"#{int(alpha * 255):02x}000000", "#dd000000"]),
        )

    def render_card():
        ph = state["phase"]
        if ph == "idle":
            card_body.content = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6,
                controls=[
                    round_icon(ft.Icons.VIDEO_FILE_OUTLINED, 54, 26),
                    ft.Container(height=2),
                    ft.Text("Click to choose a video", size=16, weight=ft.FontWeight.W_700),
                    ft.Text("Any size · any format", size=12, color=GREY),
                ])
        elif ph == "picked":
            i = state["info"]
            meta = "Reading…" if i is None else \
                f"{i.width}×{i.height} · {fmt_dur(i.duration)} · {core.fmt_mb(os.path.getsize(state['src']))}"
            card_body.content = ft.Stack(expand=True, controls=[
                thumb_image(), scrim(0.13),
                ft.Container(left=12, right=12, bottom=10, content=ft.Column(spacing=2, tight=True, controls=[
                    ft.Text(os.path.basename(state["src"]), size=14, weight=ft.FontWeight.W_700,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(meta, size=12, color=GREY),
                ])),
                ft.Container(top=8, right=8, content=round_icon(ft.Icons.SWAP_HORIZ_ROUNDED, 30, 16, True)),
            ])
        elif ph == "working":
            p = state["progress"]
            pct = int(min(max(p.fraction, 0), 1) * 100)
            sub = f"{p.speed:.1f}× realtime · under {fmt_target()}" if p.speed > 0 else f"under {fmt_target()}"
            card_body.content = ft.Stack(expand=True, controls=[
                thumb_image(), ft.Container(expand=True, bgcolor="#b8000000"),
                ft.Column(expand=True, alignment=ft.MainAxisAlignment.CENTER,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6, controls=[
                    ft.Stack(width=84, height=84, controls=[
                        ft.ProgressRing(width=84, height=84, stroke_width=6, color=WHITE, bgcolor="#26ffffff",
                                        value=None if p.fraction < 0.005 else p.fraction,
                                        stroke_cap=ft.StrokeCap.ROUND),
                        ft.Container(expand=True, alignment=ft.Alignment.CENTER,
                                     content=ft.Text(f"{pct}%", size=22, weight=ft.FontWeight.W_900)),
                    ]),
                    ft.Container(height=2),
                    ft.Text(p.stage, size=14, weight=ft.FontWeight.W_700),
                    ft.Text(sub, size=12, color=GREY),
                ]),
                ft.Container(left=12, right=12, bottom=10, content=ft.ProgressBar(
                    value=None if p.fraction < 0.005 else p.fraction, bar_height=5, color=WHITE,
                    bgcolor="#26ffffff", border_radius=8)),
            ])
        elif ph == "done":
            dst, size, plan, secs = state["result"]
            src_size = os.path.getsize(state["src"])
            ratio = src_size / size if size else 0
            detail = " · ".join([f"{plan.out_height}p" if plan.out_height else "same size",
                                 f"{plan.video_kbps} kbps", f"{secs:.0f}s",
                                 f"{ratio:.1f}× smaller"])
            card_body.content = ft.Stack(expand=True, controls=[
                thumb_image(), scrim(0.13),
                ft.Container(expand=True, alignment=ft.Alignment.CENTER,
                             content=round_icon(ft.Icons.CHECK_ROUNDED, 54, 32, True)),
                ft.Container(left=12, right=12, bottom=10, content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.END, controls=[
                        ft.Column(expand=True, spacing=1, tight=True, controls=[
                            ft.Text(core.fmt_mb(size), size=20, weight=ft.FontWeight.W_900),
                            ft.Text(f"{os.path.basename(dst)} · {os.path.dirname(dst)}", size=11,
                                    max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(detail, size=11, color=GREY),
                        ]),
                        ft.Container(content=round_icon(ft.Icons.FOLDER_OPEN_ROUNDED, 36, 18, True),
                                     on_click=lambda e: reveal(dst), tooltip="Show in Explorer"),
                    ])),
            ])
        else:  # error
            card_body.content = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6, controls=[
                    round_icon(ft.Icons.PRIORITY_HIGH_ROUNDED, 44, 24, True),
                    ft.Container(height=2),
                    ft.Text("Something went wrong", size=14, weight=ft.FontWeight.W_700),
                    ft.Text(state["error"] or "", size=11, color=GREY, text_align=ft.TextAlign.CENTER,
                            max_lines=5, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text("Click to pick another video", size=11, color=GREY),
                ])

    def reveal(path: str):
        if os.name == "nt":
            os.system(f'explorer /select,"{os.path.normpath(path)}"')

    # ---------------- presets ----------------
    tiles: dict[float, ft.Container] = {}

    def tile(mb: float):
        c = ft.Container(
            expand=True, height=40, border_radius=RS, alignment=ft.Alignment.CENTER, ink=True,
            animate=ft.Animation(220, ft.AnimationCurve.EASE_OUT_CUBIC),
            on_click=lambda e, m=mb: select_preset(m),
            content=ft.Row(alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.END,
                           spacing=3, tight=True, controls=[
                ft.Text(f"{int(mb)}", size=17, weight=ft.FontWeight.W_900),
                ft.Container(padding=ft.Padding.only(bottom=2), content=ft.Text("MB", size=10, weight=ft.FontWeight.W_700)),
            ]),
        )
        tiles[mb] = c
        return c

    custom_check = ft.Container(width=18, height=18, shape=ft.BoxShape.CIRCLE, alignment=ft.Alignment.CENTER,
                                animate=ft.Animation(220), content=ft.Icon(ft.Icons.CHECK_ROUNDED, size=12))
    custom_label = ft.Text("Custom", size=13, weight=ft.FontWeight.W_700)
    custom_field = ft.TextField(
        value=str(st.get("custom_value", "25")), width=60, text_align=ft.TextAlign.RIGHT,
        keyboard_type=ft.KeyboardType.NUMBER, border=ft.NoInputBorder(), content_padding=0,
        text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_900),
        input_filter=ft.InputFilter(regex_string=r"^[0-9.]*$"),
        on_change=lambda e: select_custom(), on_focus=lambda e: select_custom(),
    )
    custom_unit = ft.Text("MB", size=10, weight=ft.FontWeight.W_700)
    custom_tile = ft.Container(
        height=36, border_radius=RS, ink=True, animate=ft.Animation(220, ft.AnimationCurve.EASE_OUT_CUBIC),
        padding=ft.Padding.symmetric(horizontal=12), on_click=lambda e: select_custom(focus=True),
        content=ft.Row(controls=[custom_check, ft.Container(width=4), custom_label,
                                 ft.Container(expand=True), custom_field, custom_unit]),
    )

    def render_presets():
        for mb, c in tiles.items():
            sel = (not state["custom"]) and state["preset"] == mb
            c.bgcolor = WHITE if sel else BLACK
            c.border = ft.Border.all(1.5 if sel else 1, WHITE if sel else LINE)
            c.content.controls[0].color = BLACK if sel else WHITE
            c.content.controls[1].content.color = BLACK if sel else GREY
        sel = state["custom"]
        custom_tile.bgcolor = WHITE if sel else BLACK
        custom_tile.border = ft.Border.all(1.5 if sel else 1, WHITE if sel else LINE)
        custom_check.bgcolor = BLACK if sel else None
        custom_check.border = ft.Border.all(2, BLACK if sel else GREY)
        custom_check.content.color = WHITE if sel else "#00000000"
        custom_label.color = BLACK if sel else WHITE
        custom_unit.color = BLACK if sel else GREY
        custom_field.text_style = ft.TextStyle(size=15, weight=ft.FontWeight.W_900, color=BLACK if sel else WHITE)
        custom_field.cursor_color = BLACK if sel else WHITE

    def select_preset(mb: float):
        if state["phase"] == "working":
            return
        state["custom"], state["preset"] = False, mb
        persist()
        render_all()

    def select_custom(focus: bool = False):
        if state["phase"] == "working":
            return
        state["custom"] = True
        persist()
        render_all()
        if focus:
            custom_field.focus()

    # ---------------- folder row ----------------
    folder_text = ft.Text(size=12, weight=ft.FontWeight.W_700, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                          expand=True)
    reset_btn = ft.Container(
        content=ft.Text("Use Downloads", size=11, color=BLACK, weight=ft.FontWeight.W_800),
        bgcolor=WHITE, border_radius=RS, padding=ft.Padding.symmetric(horizontal=10, vertical=5), ink=True,
        tooltip="Save to Downloads again", on_click=lambda e: reset_folder(), margin=ft.Margin.only(right=4))
    folder_row = ft.Container(
        height=36, border_radius=RS, border=ft.Border.all(1, LINE), ink=True,
        padding=ft.Padding.only(left=10, right=4), on_click=lambda e: page.run_task(pick_folder),
        content=ft.Row(controls=[
            ft.Icon(ft.Icons.FOLDER_ROUNDED, size=15, color=WHITE), ft.Container(width=0),
            ft.Text("Save to", size=12, color=GREY), folder_text, reset_btn,
        ]),
    )

    def render_folder():
        folder_text.value = state["out_dir"]
        folder_text.tooltip = state["out_dir"]
        reset_btn.visible = os.path.normcase(state["out_dir"]) != os.path.normcase(downloads_dir())

    def reset_folder():
        state["out_dir"] = downloads_dir()
        persist()
        render_all()

    async def pick_folder():
        if state["phase"] == "working":
            return
        d = await picker.get_directory_path(dialog_title="Save videos to", initial_directory=state["out_dir"])
        if d:
            state["out_dir"] = d
            persist()
            render_all()

    # ---------------- big button ----------------
    go_label = ft.Text("Squish It", size=15, weight=ft.FontWeight.W_700)
    go_btn = ft.Container(
        height=42, border_radius=R, alignment=ft.Alignment.CENTER, ink=True,
        border=ft.Border.all(1.5, WHITE), animate=ft.Animation(250), animate_opacity=250,
        on_click=lambda e: page.run_task(go),
        content=go_label,
    )

    def render_button():
        working = state["phase"] == "working"
        can = state["src"] is not None and state["info"] is not None and target_ok() and not working
        go_btn.bgcolor = BLACK if working else WHITE
        go_btn.opacity = 1 if (can or working) else 0.35
        fg = WHITE if working else BLACK
        go_label.value = "Cancel" if working else ("Squish It again" if state["phase"] == "done" else f"Squish It to {fmt_target()}" if target_ok() else "Squish It")
        go_label.color = fg

    def render_all():
        render_card()
        render_presets()
        render_folder()
        render_button()
        page.update()

    # ---------------- actions ----------------
    async def pick_video(e=None):
        if state["phase"] == "working":
            return
        files = await picker.pick_files(
            dialog_title="Choose a video", file_type=ft.FilePickerFileType.VIDEO,
            initial_directory=os.path.dirname(state["src"]) if state["src"] else None)
        if not files or not files[0].path:
            return
        await load_video(files[0].path)

    async def load_video(path: str):
        state.update(src=path, info=None, thumb=None, result=None, error=None, phase="picked")
        render_all()
        try:
            info = await asyncio.to_thread(core.probe, state["src"])
            tp = os.path.join(tempfile.gettempdir(), f"squish_thumb_{int(time.time()*1000)}.jpg")
            ok = await asyncio.to_thread(core.Job().thumbnail, state["src"], info.duration, tp)
            thumb = None
            if ok:
                with open(tp, "rb") as f:
                    thumb = f.read()
                try:
                    os.remove(tp)
                except OSError:
                    pass
            state.update(info=info, thumb=thumb)
        except Exception as ex:
            state.update(error=f"Could not read that video.\n{ex}", phase="error")
        render_all()

    async def go():
        if state["phase"] == "working":
            if state["job"]:
                state["job"].cancel()
            return
        if not (state["src"] and state["info"] and target_ok()):
            return
        persist()
        job = core.Job()
        state.update(job=job, phase="working", error=None, result=None,
                     progress=core.Progress("Starting", 0.0, 0.0))
        render_all()
        loop = asyncio.get_running_loop()
        last = [0.0]

        def on_progress(p: core.Progress):
            now = time.time()
            if now - last[0] < 0.1 and p.fraction < 0.98:
                return
            last[0] = now
            state["progress"] = p
            loop.call_soon_threadsafe(lambda: (render_card(), page.update()))

        try:
            res = await asyncio.to_thread(job.squish, state["src"], state["info"], target_mb(),
                                          state["out_dir"], on_progress)
            state.update(result=res, phase="done")
        except core.Cancelled:
            state["phase"] = "picked"
        except Exception as ex:
            state.update(error=str(ex), phase="error")
        state["job"] = None
        render_all()

    card.on_click = lambda e: page.run_task(pick_video)

    # ---------------- layout ----------------
    def caps(t):
        return ft.Container(padding=ft.Padding.only(left=2), content=ft.Text(
            t.upper(), size=11, color=GREY, weight=ft.FontWeight.W_700, style=ft.TextStyle(letter_spacing=1.3)))

    async def minimize(e):
        page.window.minimized = True
        page.update()

    async def close(e):
        if state["job"]:
            state["job"].cancel()
        await page.window.close()

    title_bar = ft.Container(
        ft.Row([
            ft.WindowDragArea(
                ft.Container(ft.Row([
                    ft.Image(src=ico, width=22, height=22) if os.path.exists(ico) else ft.Container(),
                    ft.Text("squish", size=26, color=WHITE, weight=ft.FontWeight.W_900),
                    ft.Container(padding=ft.Padding.only(top=6), content=ft.Text(
                        "simple video compressor", size=12, color=GREY, italic=True, weight=ft.FontWeight.W_600)),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding.only(left=10, top=2, bottom=2)),
                expand=True, maximizable=False),
            ft.IconButton(ft.Icons.REMOVE, icon_color=GREY, icon_size=15, hover_color=HOVER, on_click=minimize,
                          tooltip="Minimize", visual_density=ft.VisualDensity.COMPACT),
            ft.IconButton(ft.Icons.CLOSE, icon_color=GREY, icon_size=15, hover_color=HOVER, on_click=close,
                          tooltip="Close", visual_density=ft.VisualDensity.COMPACT),
            ft.Container(width=2),
        ], spacing=0),
        border=ft.Border.only(bottom=ft.BorderSide(1, LINE)),
    )
    body = ft.Container(expand=True, padding=ft.Padding.only(left=10, right=10, top=8, bottom=10), content=ft.Column(
        expand=True, spacing=6, controls=[
            card,
            caps("Size limit"),
            ft.Row(spacing=6, controls=[tile(float(m)) for m in PRESETS]),
            custom_tile,
            caps("Save to"), folder_row,
            go_btn,
        ]))
    shots_mode = "--shots" in sys.argv
    root = ft.Screenshot(content=ft.Container(
        bgcolor=BLACK, expand=not shots_mode,
        width=400 if shots_mode else None, height=470 if shots_mode else None,
        content=ft.Column([title_bar, body], spacing=0, expand=True)))
    page.add(root)

    # Preload a file given on the command line (also lets "Open with" work).
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and os.path.isfile(args[0]) and "--shots" not in sys.argv and "--auto" not in sys.argv:
        page.run_task(load_video, args[0])

    # Hidden: `squish_app.py <video> --shots DIR` renders idle/picked/working/done PNGs (no OS capture needed).
    if "--shots" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--shots") + 1]

        async def snap(name):
            await asyncio.sleep(0.6)
            data = await root.capture(pixel_ratio=2.0)
            with open(os.path.join(out_dir, name), "wb") as f:
                f.write(data)

        async def shots():
            os.makedirs(out_dir, exist_ok=True)
            await asyncio.sleep(1.0)
            await snap("windows-1-idle.png")
            await load_video(args[0])
            await snap("windows-2-picked.png")
            task = page.run_task(go)
            for _ in range(60):
                await asyncio.sleep(0.5)
                if state["phase"] == "working" and 0.15 < state["progress"].fraction < 0.4:
                    break
            await snap("windows-3-working.png")
            await task
            await snap("windows-4-done.png")
            print("SHOTS_DONE", flush=True)
            await page.window.close()
        page.run_task(shots)

    # Hidden self-test: `squish_app.py <video> --auto [--mb N]` squishes it and prints the result.
    if "--auto" in sys.argv:
        async def auto():
            if "--mb" in sys.argv:
                custom_field.value = sys.argv[sys.argv.index("--mb") + 1]
                state["custom"] = True
            await load_video(args[0])
            await go()
            print("AUTO_RESULT", json.dumps({"phase": state["phase"], "error": state["error"],
                  "result": None if not state["result"] else [state["result"][0], state["result"][1], round(state["result"][3], 1)]}), flush=True)
            await page.window.close()
        page.run_task(auto)
    render_all()


if __name__ == "__main__":
    ft.run(main)
