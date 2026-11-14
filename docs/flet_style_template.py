"""Starter template for the Squish desktop look (Flet 1.x). Run: python flet_style_template.py

Shows every building block: custom title bar, outlined card, section captions, chips,
inline-number row, slider section with header, outlined row with a pill action, primary button,
and a fake 'working' state with a progress ring. Replace the demo logic with your own.
"""
from __future__ import annotations

import asyncio
import os
import sys

import flet as ft

# ---- palette / sizing ------------------------------------------------------------------------
WHITE, BLACK, GREY, LINE = "#FFFFFF", "#000000", "#9A9A9A", "#3A3A3A"
TRACK_OFF, HOVER = "#5A5A5A", "#1AFFFFFF"
R, RS = 12, 8
WIN_W, WIN_H = 400, 560
APP_NAME, TAGLINE = "myapp", "one line about it"


def theme() -> ft.Theme:
    return ft.Theme(
        font_family="Segoe UI",
        color_scheme=ft.ColorScheme(primary=WHITE, on_primary=BLACK, surface=BLACK, on_surface=WHITE, outline=WHITE),
        slider_theme=ft.SliderTheme(
            track_height=8, active_track_color=WHITE, inactive_track_color=TRACK_OFF, thumb_color=WHITE,
            overlay_color="#33FFFFFF", active_tick_mark_color="#00000000", inactive_tick_mark_color="#00000000",
            disabled_active_tick_mark_color="#00000000", disabled_inactive_tick_mark_color="#00000000",
            disabled_active_track_color=LINE, disabled_inactive_track_color=LINE, disabled_thumb_color=GREY,
        ),
    )


# ---- reusable widgets ------------------------------------------------------------------------
def caption(text: str) -> ft.Control:
    """Section caption: small grey caps with letter spacing."""
    return ft.Container(padding=ft.Padding.only(left=2), content=ft.Text(
        text.upper(), size=11, color=GREY, weight=ft.FontWeight.W_700, style=ft.TextStyle(letter_spacing=1.3)))


def label(text: str, size: int = 12, color: str = WHITE) -> ft.Text:
    return ft.Text(text, size=size, color=color, weight=ft.FontWeight.W_700)


def round_icon(icon, size: float, icon_size: float, filled: bool = False) -> ft.Container:
    return ft.Container(
        width=size, height=size, shape=ft.BoxShape.CIRCLE, alignment=ft.Alignment.CENTER,
        bgcolor=WHITE if filled else None, border=None if filled else ft.Border.all(2.5, WHITE),
        content=ft.Icon(icon, size=icon_size, color=BLACK if filled else WHITE))


def chip(text: str, on_click, height: int = 38, big: bool = True) -> ft.Container:
    """Selectable tile. Call paint_chip(c, selected) to colour it."""
    return ft.Container(
        expand=big, height=height, border_radius=RS, alignment=ft.Alignment.CENTER, ink=True,
        padding=None if big else ft.Padding.symmetric(horizontal=9),
        animate=ft.Animation(220, ft.AnimationCurve.EASE_OUT_CUBIC), on_click=on_click,
        content=ft.Text(text, size=17 if big else 11, weight=ft.FontWeight.W_900 if big else ft.FontWeight.W_800))


def paint_chip(c: ft.Container, selected: bool) -> None:
    c.bgcolor = WHITE if selected else BLACK
    c.border = ft.Border.all(1.5 if selected else 1, WHITE if selected else LINE)
    c.content.color = BLACK if selected else WHITE


def small_input(width: int = 76, on_done=None, pattern: str = r"^[0-9:.]*$") -> ft.TextField:
    """Compact outlined input. Wrap in Container(padding=top 4) when next to plain labels."""
    def select_all(e):
        e.control.selection = ft.TextSelection(base_offset=0, extent_offset=len(e.control.value or ""))
        e.control.page.update()
    return ft.TextField(
        value="", width=width, height=30, dense=True, text_align=ft.TextAlign.CENTER,
        content_padding=ft.Padding.symmetric(horizontal=4, vertical=0),
        text_style=ft.TextStyle(size=12, weight=ft.FontWeight.W_700, color=WHITE), cursor_color=WHITE,
        border={ft.ControlState.FOCUSED: ft.OutlineInputBorder(side=ft.BorderSide(1.5, WHITE), border_radius=6),
                ft.ControlState.DEFAULT: ft.OutlineInputBorder(side=ft.BorderSide(1, LINE), border_radius=6)},
        input_filter=ft.InputFilter(regex_string=pattern),
        on_focus=select_all, on_submit=on_done, on_blur=on_done)


def pill(text: str, on_click) -> ft.Container:
    """White pill action used inside outlined rows."""
    return ft.Container(
        content=ft.Text(text, size=11, color=BLACK, weight=ft.FontWeight.W_800), bgcolor=WHITE, border_radius=RS,
        padding=ft.Padding.symmetric(horizontal=10, vertical=5), ink=True, on_click=on_click,
        margin=ft.Margin.only(right=4))


def outlined_row(controls: list[ft.Control], on_click=None, height: int = 34) -> ft.Container:
    return ft.Container(
        height=height, border_radius=RS, border=ft.Border.all(1, LINE), ink=True, on_click=on_click,
        padding=ft.Padding.only(left=10, right=4), content=ft.Row(controls=controls))


def primary_button(text: str, on_click) -> tuple[ft.Container, ft.Text]:
    lbl = ft.Text(text, size=15, weight=ft.FontWeight.W_700, color=BLACK)
    btn = ft.Container(
        height=42, border_radius=R, alignment=ft.Alignment.CENTER, ink=True, bgcolor=WHITE,
        border=ft.Border.all(1.5, WHITE), animate=ft.Animation(250), animate_opacity=250,
        on_click=on_click, content=lbl)
    return btn, lbl


def paint_button(btn: ft.Container, lbl: ft.Text, enabled: bool, working: bool, text: str) -> None:
    btn.bgcolor = BLACK if working else WHITE
    btn.opacity = 1 if (enabled or working) else 0.35
    lbl.value, lbl.color = text, (WHITE if working else BLACK)


def title_bar(page: ft.Page, icon_path: str | None, on_close) -> ft.Container:
    async def minimize(e):
        page.window.minimized = True
        page.update()
    left = ft.Row([
        ft.Image(src=icon_path, width=22, height=22) if icon_path and os.path.exists(icon_path) else ft.Container(),
        ft.Text(APP_NAME, size=26, color=WHITE, weight=ft.FontWeight.W_900),
        ft.Container(padding=ft.Padding.only(top=6), content=ft.Text(
            TAGLINE, size=12, color=GREY, italic=True, weight=ft.FontWeight.W_600)),
    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    return ft.Container(
        ft.Row([
            ft.WindowDragArea(ft.Container(left, padding=ft.Padding.only(left=10, top=2, bottom=2)),
                              expand=True, maximizable=False),
            ft.IconButton(ft.Icons.REMOVE, icon_color=GREY, icon_size=15, hover_color=HOVER, on_click=minimize,
                          tooltip="Minimize", visual_density=ft.VisualDensity.COMPACT),
            ft.IconButton(ft.Icons.CLOSE, icon_color=GREY, icon_size=15, hover_color=HOVER, on_click=on_close,
                          tooltip="Close", visual_density=ft.VisualDensity.COMPACT),
            ft.Container(width=2),
        ], spacing=0),
        border=ft.Border.only(bottom=ft.BorderSide(1, LINE)))


# ---- demo app --------------------------------------------------------------------------------
async def main(page: ft.Page):
    page.title = APP_NAME
    page.bgcolor, page.padding, page.theme_mode = BLACK, 0, ft.ThemeMode.DARK
    w = page.window
    w.width, w.height = WIN_W, WIN_H
    w.resizable = w.maximizable = False
    w.title_bar_hidden = True
    w.bgcolor = BLACK
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists(os.path.join(base, "icon.ico")):
        w.icon = os.path.join(base, "icon.ico")
    page.theme = page.dark_theme = theme()

    state = {"preset": 10, "custom": False, "level": 3, "working": False}

    # Card (big outlined panel) -----------------------------------------------------------
    card_body = ft.Container(expand=True, alignment=ft.Alignment.CENTER, padding=ft.Padding.symmetric(vertical=14))
    card = ft.Container(expand=True, min_height=150, border_radius=R, border=ft.Border.all(1.5, WHITE),
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS, ink=True, content=card_body,
                        on_click=lambda e: page.run_task(fake_work))

    def render_card():
        if state["working"]:
            card_body.content = ft.Stack(expand=True, controls=[
                ft.Container(expand=True, bgcolor="#b8000000"),
                ft.Column(expand=True, alignment=ft.MainAxisAlignment.CENTER,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6, controls=[
                    ft.Stack(width=84, height=84, controls=[
                        ft.ProgressRing(width=84, height=84, stroke_width=6, color=WHITE, bgcolor="#26ffffff",
                                        value=state.get("progress"), stroke_cap=ft.StrokeCap.ROUND),
                        ft.Container(expand=True, alignment=ft.Alignment.CENTER, content=ft.Text(
                            f"{int((state.get('progress') or 0) * 100)}%", size=22, weight=ft.FontWeight.W_900)),
                    ]),
                    ft.Text("Working", size=14, weight=ft.FontWeight.W_700),
                ]),
                ft.Container(left=12, right=12, bottom=10, content=ft.ProgressBar(
                    value=state.get("progress"), bar_height=5, color=WHITE, bgcolor="#26ffffff", border_radius=8)),
            ])
        else:
            card_body.content = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6,
                controls=[round_icon(ft.Icons.TOUCH_APP_OUTLINED, 54, 26),
                          ft.Container(height=2),
                          ft.Text("Click to do the thing", size=16, weight=ft.FontWeight.W_700),
                          ft.Text("Secondary hint", size=12, color=GREY)])

    # Chips ------------------------------------------------------------------------------
    chips: dict[int, ft.Container] = {}
    for v in (5, 8, 10, 20):
        chips[v] = chip(str(v), on_click=lambda e, v=v: select(v))

    def select(v: int):
        state["preset"], state["custom"] = v, False
        render_all()

    # Inline-number row ("Custom") ---------------------------------------------------------
    check = ft.Container(width=18, height=18, shape=ft.BoxShape.CIRCLE, alignment=ft.Alignment.CENTER,
                         animate=ft.Animation(220), content=ft.Icon(ft.Icons.CHECK_ROUNDED, size=12))
    custom_label = ft.Text("Custom", size=13, weight=ft.FontWeight.W_700)
    custom_field = ft.TextField(
        value="25", width=56, height=36, dense=True, text_align=ft.TextAlign.RIGHT, text_vertical_align=0.0,
        keyboard_type=ft.KeyboardType.NUMBER, border=ft.NoInputBorder(),
        content_padding=ft.Padding.symmetric(horizontal=2, vertical=0),
        text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_900),
        input_filter=ft.InputFilter(regex_string=r"^[0-9.]*$"),
        on_focus=lambda e: select_custom(), on_change=lambda e: select_custom())
    custom_unit = ft.Text("MB", size=10, weight=ft.FontWeight.W_700)
    custom_tile = ft.Container(
        height=36, border_radius=RS, ink=True, animate=ft.Animation(220, ft.AnimationCurve.EASE_OUT_CUBIC),
        padding=ft.Padding.symmetric(horizontal=12), on_click=lambda e: select_custom(),
        content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
            check, ft.Container(width=4), custom_label, ft.Container(expand=True),
            ft.Container(padding=ft.Padding.only(top=2), content=custom_field), custom_unit]))

    def select_custom():
        state["custom"] = True
        render_all()

    def render_chips():
        for v, c in chips.items():
            paint_chip(c, (not state["custom"]) and state["preset"] == v)
        sel = state["custom"]
        custom_tile.bgcolor = WHITE if sel else BLACK
        custom_tile.border = ft.Border.all(1.5 if sel else 1, WHITE if sel else LINE)
        check.bgcolor = BLACK if sel else None
        check.border = ft.Border.all(2, BLACK if sel else GREY)
        check.content.color = WHITE if sel else "#00000000"
        custom_label.color = BLACK if sel else WHITE
        custom_unit.color = BLACK if sel else GREY
        custom_field.text_style = ft.TextStyle(size=15, weight=ft.FontWeight.W_900, color=BLACK if sel else WHITE)
        custom_field.cursor_color = BLACK if sel else WHITE

    # Slider section (header row + full-width slider) ---------------------------------------
    level_val = ft.Text("3", size=13, weight=ft.FontWeight.W_800)
    level_slider = ft.Slider(min=0, max=10, divisions=10, value=3, expand=True,
                             padding=ft.Padding.symmetric(horizontal=0))

    def on_level(e):
        state["level"] = int(round(level_slider.value))
        level_val.value = str(state["level"])
        page.update()
    level_slider.on_change = on_level

    # Small inputs next to labels ----------------------------------------------------------
    start_f, end_f = small_input(), small_input()
    start_f.value, end_f.value = "00:00:00", "00:01:00"
    inputs_row = ft.Row(spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, height=32, controls=[
        label("Range"), ft.Container(expand=True),
        label("Start", 11, GREY), ft.Container(padding=ft.Padding.only(top=4), content=start_f),
        ft.Container(width=6),
        label("End", 11, GREY), ft.Container(padding=ft.Padding.only(top=4), content=end_f)])

    # Outlined row with a pill -------------------------------------------------------------
    folder_text = ft.Text("C:\\Users\\you\\Downloads", size=12, weight=ft.FontWeight.W_700, expand=True,
                          max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    folder_row = outlined_row([
        ft.Icon(ft.Icons.FOLDER_ROUNDED, size=15, color=WHITE), ft.Container(width=0),
        ft.Text("Save to", size=12, color=GREY), folder_text, pill("Use Downloads", lambda e: None)])

    # Primary button -----------------------------------------------------------------------
    go_btn, go_lbl = primary_button("Do It", lambda e: page.run_task(fake_work))

    async def fake_work():
        if state["working"]:
            return
        state["working"] = True
        for i in range(0, 101, 5):
            state["progress"] = i / 100
            render_all()
            await asyncio.sleep(0.05)
        state["working"] = False
        render_all()

    def render_all():
        render_card()
        render_chips()
        paint_button(go_btn, go_lbl, enabled=True, working=state["working"],
                     text="Cancel" if state["working"] else f"Do It at {state['preset'] if not state['custom'] else custom_field.value} MB")
        page.update()

    async def close(e):
        await page.window.close()

    body = ft.Container(expand=True, padding=ft.Padding.only(left=10, right=10, top=8, bottom=10), content=ft.Column(
        expand=True, spacing=5, controls=[
            card,
            caption("Level"),
            ft.Row(controls=[label("Level"), ft.Container(expand=True), level_val], height=22),
            ft.Container(content=level_slider, height=30, padding=ft.Padding.symmetric(horizontal=2)),
            inputs_row,
            caption("Size limit"),
            ft.Row(spacing=6, controls=list(chips.values())),
            custom_tile,
            caption("Save to"), folder_row,
            go_btn,
        ]))
    page.add(ft.Column([title_bar(page, os.path.join(base, "icon.png"), close), body], spacing=0, expand=True))
    render_all()


if __name__ == "__main__":
    ft.run(main)
