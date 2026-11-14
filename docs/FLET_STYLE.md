# Squish desktop UI — style guide (Flet 1.x)

Runnable starter with every block below: [`flet_style_template.py`](flet_style_template.py)
(`python docs/flet_style_template.py`). Copy its helper functions into a new app.

A compact, single-screen, black-and-white desktop look. Everything fits in one fixed window, no
scrolling, no sub-screens, no dropdowns. Copy this into any Flet app.

## Palette and type

| Token | Value | Use |
|---|---|---|
| `BLACK` | `#000000` | window, panels, selected-chip text |
| `WHITE` | `#FFFFFF` | text, outlines, selected chips, primary button, slider track |
| `GREY` | `#9A9A9A` | secondary text, section captions, unit labels |
| `LINE` | `#3A3A3A` | 1 px borders of unselected chips/rows, title-bar divider |
| `#5A5A5A` | | inactive slider track |
| `HOVER` | `#1AFFFFFF` | icon-button hover |

Font: Segoe UI. Weights: W_900 for the wordmark and numbers, W_800/W_700 for labels and buttons,
W_600 italic for the tagline. Sizes: wordmark 26, primary button 15, row text 12–13, captions 11.

Radii: 12 (`R`) for the big card and primary button, 8 (`RS`) for chips, rows and tiles, 6 for
small inputs and icon box.

## Window

```python
page.bgcolor = BLACK; page.padding = 0; page.theme_mode = ft.ThemeMode.DARK
w = page.window
w.width, w.height = 400, 700        # fixed, compact
w.resizable = w.maximizable = False
w.title_bar_hidden = True            # we draw our own
w.bgcolor = BLACK
w.icon = "icon.ico"                  # taskbar icon (also pass --icon to `flet pack`)
page.theme = page.dark_theme = ft.Theme(
    font_family="Segoe UI",
    color_scheme=ft.ColorScheme(primary=WHITE, on_primary=BLACK, surface=BLACK,
                                on_surface=WHITE, outline=WHITE),
    slider_theme=ft.SliderTheme(
        track_height=8, active_track_color=WHITE, inactive_track_color="#5A5A5A",
        thumb_color=WHITE, overlay_color="#33FFFFFF",
        active_tick_mark_color="#00000000", inactive_tick_mark_color="#00000000",
        disabled_active_tick_mark_color="#00000000", disabled_inactive_tick_mark_color="#00000000",
        disabled_active_track_color=LINE, disabled_inactive_track_color=LINE, disabled_thumb_color=GREY),
)
```

Add the root as `page.add(ft.Column([title_bar, body], spacing=0, expand=True))`. Do not wrap it in
`ft.Screenshot` or another non-layout control: it will not expand and leaves dead space.

## Custom title bar

Row: 22 px icon image, wordmark `squish` (26, W_900), italic grey tagline, spacer, two compact
`IconButton`s (REMOVE, CLOSE; `icon_size=15`, `icon_color=GREY`, `hover_color=HOVER`,
`visual_density=COMPACT`). The left part is wrapped in `ft.WindowDragArea(..., maximizable=False)`
so the window can be moved. Bottom border `ft.Border.only(bottom=ft.BorderSide(1, LINE))`.

## Layout rhythm

`body = ft.Container(expand=True, padding=Padding.only(left=10, right=10, top=8, bottom=10))`
holding a `Column(spacing=5)`:

1. Big outlined card (`expand=True, min_height=180, border=Border.all(1.5, WHITE), border_radius=12,
   clip_behavior=ANTI_ALIAS, ink=True`). Idle content gets `padding=Padding.symmetric(vertical=14)`.
2. Section caption: `Text(t.upper(), size=11, color=GREY, weight=W_700, style=TextStyle(letter_spacing=1.3))`
   with `Padding.only(left=2)`.
3. Controls for that section.
4. Primary button at the bottom.

## Components

**Chip / preset tile** (selectable): `Container(height=38, border_radius=8, ink=True,
animate=Animation(220, EASE_OUT_CUBIC))`. Selected: `bgcolor=WHITE, border=Border.all(1.5, WHITE)`,
text BLACK. Unselected: `bgcolor=BLACK, border=Border.all(1, LINE)`, text WHITE (unit label GREY).
Small chips (crop style): height 24–28, `padding=Padding.symmetric(horizontal=9)`, text 11 W_800.

**Row with an inline input** (custom size): `Container(height=36, border_radius=8, padding=symmetric(h=12))`
containing a `Row(vertical_alignment=CENTER)`: 18 px circle check (`shape=CIRCLE`, border 2),
label, spacer, `TextField(width=56, height=36, dense=True, text_vertical_align=0.0,
border=ft.NoInputBorder(), content_padding=Padding.symmetric(horizontal=2, vertical=0),
text_style=TextStyle(size=15, weight=W_900))`, unit text (10, W_700).
Wrap the field in `Container(padding=Padding.only(top=2))`: Flet text fields render a couple of px
high inside their row, so nudge them down to sit on the label baseline.

**Small time/number box**: `TextField(width=76, height=30, dense=True, text_align=CENTER,
content_padding=symmetric(h=4, v=0), text_style=TextStyle(size=12, weight=W_700),
border={FOCUSED: OutlineInputBorder(BorderSide(1.5, WHITE), radius 6),
        DEFAULT: OutlineInputBorder(BorderSide(1, LINE), radius 6)},
input_filter=InputFilter(r"^[0-9:.]*$"), on_focus=select_all, on_submit=..., on_blur=...)`.
Wrap in `Container(padding=Padding.only(top=4))` next to plain text labels. `select_all` sets
`tf.selection = ft.TextSelection(base_offset=0, extent_offset=len(tf.value))` so typing replaces.

**Slider sections**: header row `Row([label(12, W_700, WHITE), spacer, value(13, W_800)], height=22)`,
then the slider alone in a `Container(height=30, padding=symmetric(horizontal=2))` so the track
spans the full width. Snap sliders use `divisions`. Never grey a slider out; keep it enabled-looking
and have the handler ignore input until there is something to edit.

**Outlined row** (folder picker style): `Container(height=34, border_radius=8, border=Border.all(1, LINE),
ink=True, padding=Padding.only(left=10, right=4))` with icon 15, grey lead-in text 12, bold value
(expand, ellipsis), and an optional white pill action: `Container(bgcolor=WHITE, border_radius=8,
padding=symmetric(h=10, v=5), content=Text(size=11, color=BLACK, weight=W_800))`.

**Primary button**: `Container(height=42, border_radius=12, alignment=CENTER, ink=True,
border=Border.all(1.5, WHITE), bgcolor=WHITE, animate=Animation(250), animate_opacity=250,
content=Text(size=15, weight=W_700, color=BLACK))`. Text only, no icons. Disabled = `opacity=0.35`.
While working it inverts (black bg, white text, label "Cancel").

**Round icon badge**: `Container(width=s, height=s, shape=CIRCLE, bgcolor=WHITE or border 2.5 WHITE,
content=Icon(size, color=BLACK or WHITE))`.

**Progress state**: dim the card (`#b8000000` overlay), 84 px `ProgressRing(stroke_width=6,
color=WHITE, bgcolor="#26ffffff", stroke_cap=ROUND)` with the percent (22, W_900) centred inside,
stage text below, and a 5 px `ProgressBar(color=WHITE, bgcolor="#26ffffff", border_radius=8)` at the
card's bottom. Throttle UI updates from worker threads to ~10/s with `loop.call_soon_threadsafe`.

## Behaviour conventions

- Settings persist to `%APPDATA%\<App>\settings.json`; reload on start.
- Long work runs in `asyncio.to_thread`; the UI thread only re-renders.
- Re-render by mutating existing controls and calling `page.update()`; keep one instance of heavy
  controls (images) and reuse it instead of recreating it on every tick.
- Hidden CLI hooks for testing without a mouse: `--auto` (run and print a result) and `--shots DIR`
  (render each state with `ft.Screenshot.capture()`), run with `FLET_HIDE_WINDOW_ON_START=true`.

## Packaging

```
flet pack app.py --name App --icon icon.ico --product-name "App" --add-data "icon.ico;." --add-data "icon.png;." -y
```

Single portable exe; `--icon` gives the file and taskbar their icon.
