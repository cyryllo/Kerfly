"""
Light and dark look of the window (Settings → View → Theme; applies after a
restart, like the language). The laser bed itself stays light in both: it
stands for the material, and designs are drawn on it in their real colours.

Everything the window's look is made of lives here, so the rest of the GUI
never names a colour or a size of its own:

- sizes (px, the same in both themes): icons, spacing, heights, rounding;
- TOKENS: the colours of the window, light and dark;
- CANVAS: the colours drawn on the bed, the simulation and the previews
  (the same in both themes, as the bed is);
- STYLE: the style sheet; widgets take a part of it by their object name or
  by their "role" property (widgets.py sets those).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from string import Template

from kerfly.i18n import N_

# (setting value, name shown in Settings)
THEMES = [("light", N_("Light")), ("dark", N_("Dark")), ("system", N_("As the system"))]
DEFAULT = "light"

# ---- sizes (px) ---------------------------------------------------------------------------------
ICON_SMALL = 16          # an icon inside a text button ("+ Add layer"), a list row
ICON = 20                # small icon buttons, field captions, the options bar
ICON_LARGE = 24          # big ribbon buttons, the drawing tools strip
SPACE_S = 4              # between the parts of one control (icon and its caption)
SPACE_M = 8              # between controls in a row
SPACE_L = 12             # around a panel or a dialog's sections
SPACE_ROW = 6            # between the rows of a form
PAD_DIALOG = 16          # inside a dialog's body
HEIGHT_FIELD = 28        # fields, small icon buttons, list rows
HEIGHT_BUTTON = 32       # text buttons of a dialog's footer
HEIGHT_ACTION = 44       # the job's buttons (Trace, Start, Pause, Stop), a dialog's preview bar
HEIGHT_OPTION_ROW = 36   # one row of the options bar
RIBBON_BUTTON = 56       # a big ribbon button (an icon over its label)
OPTION_TITLE = 96        # the bold name at the start of a row of the options bar
PANEL_WIDTH = 400        # the left panel (Design and Laser tabs), at least
PANEL_ROOM = 50          # the left panel: this much wider than its content needs (layer names, lists)
RADIUS = 4               # rounded corners of buttons, fields and frames
BUTTON_MIN_WIDTH = 88    # a dialog's footer buttons
DIALOG_SMALL = 440       # the width of a small dialog (a question, a few fields)
DIALOG_LARGE = 760       # the width of a large dialog (lists, settings, a preview)

TOKENS = {
    "light": {
        # surfaces
        "window": "#f4f5f7", "panel": "#ffffff", "top_bar": "#eef0f3", "bar_light": "#f7f8fa",
        "top_border": "#c4c9d0", "separator": "#c4c9d0", "field_border": "#b6bcc5", "divider": "#e1e4e8",
        "hover": "#dfe3e8",
        # text and icons
        "ink": "#2b2f36", "arrow": "#202124", "hint": "#4b5563", "caption": "#5b6370", "disabled": "#7a818c",
        "accent": "#2f6aa8", "accent_dark": "#1f4f82",
        # the named action of a dialog (white text on it)
        "primary": "#2f6aa8", "primary_hover": "#1f4f82",
        # a button that is on (a tool, the aspect lock)
        "on_bg": "#dce6f2", "on_border": "#9db8d6", "on_ink": "#1f4f82",
        # states
        "ok": "#2e7d32", "error": "#c62828", "danger": "#b3261e", "danger_border": "#d9a3a0",
        "warn_bg": "#fff4e0", "warn_ink": "#5c3d00", "warn_border": "#e0b266", "fire": "#e65100",
        "update_bg": "#e3f2fd", "update_border": "#90caf9",
        # the job's buttons
        "start": "#2e7d32", "start_border": "#256b29", "stop": "#c62828", "stop_border": "#a32020",
        "action_ink": "#ffffff", "start_off": "#9e9e9e", "stop_off": "#bdbdbd", "off_bg": "#eceef1",
        "swatch_border": "#555555",
    },
    "dark": {
        "window": "#30343a", "panel": "#2b2f34", "top_bar": "#2b2f35", "bar_light": "#2b2f34",
        "top_border": "#1b1e22", "separator": "#4a505a", "field_border": "#5a606a", "divider": "#3a3f46",
        "hover": "#3a3f46",
        "ink": "#d9dce1", "arrow": "#e3e6ea", "hint": "#b4bac3", "caption": "#9aa1ab", "disabled": "#7a8089",
        "accent": "#5a9bd8", "accent_dark": "#2f6aa8",
        "primary": "#2f6aa8", "primary_hover": "#3a7cc0",
        "on_bg": "#22405f", "on_border": "#2f6aa8", "on_ink": "#cfe2f7",
        "ok": "#66bb6a", "error": "#ef5350", "danger": "#ef5350", "danger_border": "#7a3a38",
        "warn_bg": "#3d3220", "warn_ink": "#ffd27a", "warn_border": "#7a6230", "fire": "#ff8a3d",
        "update_bg": "#1d3a5c", "update_border": "#2f6aa8",
        "start": "#2e7d32", "start_border": "#1f5a23", "stop": "#c62828", "stop_border": "#8e1c1c",
        "action_ink": "#ffffff", "start_off": "#4a4f56", "stop_off": "#4a4f56", "off_bg": "#383d44",
        "swatch_border": "#9aa1ab",
    },
}

# drawn on the bed, the simulation and the previews: the same in both themes (the bed stands for the
# material); the layers' own colours are the design's data (kerfly/core/layers.py), not here
CANVAS = {
    "bed": "#e9ebee", "bed_border": "#b8bec7", "background": "#5b616b", "grid_minor": "#d3d7dd",
    "grid_major": "#bfc5cd", "engrave": "#1565c0", "cut": "#d32f2f", "gcode": "#6a1b9a",
    "outline": "#9aa1ab", "selection": "#1e88e5", "head": "#f57c00", "off_bed": "#d32f2f",
    "snap": "#e040fb", "handle": "#ffffff",
    # the simulation: red where the laser is on, grey for moves with it off
    "burn": "#e53935", "move": "#9e9e9e",
    # the previews of the generators, the image trace and the 3D box
    "preview_bg": "#e9ebef", "preview_paper": "#ffffff", "preview_line": "#d32f2f", "box3d_bg": "#eef0f3",
    "wood": ["#d9b98c", "#cfa977", "#e3c79d", "#c99f6c"],
}

STYLE = Template("""
QPushButton#start { background:$start; color:$action_ink; font-weight:600; border: 1px solid $start_border;
                    border-radius:${radius}px; }
QPushButton#stop { background:$stop; color:$action_ink; font-weight:600; border: 1px solid $stop_border;
                   border-radius:${radius}px; }
QPushButton#trace, QPushButton#pause { background: $panel; border: 1px solid $field_border;
                                       border-radius:${radius}px; }
QPushButton#trace:hover, QPushButton#pause:hover { background: $top_bar; }
QPushButton#start:disabled, QPushButton#stop:disabled, QPushButton#pause:disabled, QPushButton#trace:disabled {
    background: $off_bg; color: $caption; border: 1px solid $separator; }
QPushButton#start { font-size: 13px; }

/* the left panel (docs/ui-mockups/Main, LaserTab): flat, white, tabs underlined, the job's bar at the bottom */
QWidget#left_panel { background: $panel; }
QTabWidget#panel_tabs::pane { border: 0px; border-top: 1px solid $separator; }
QTabWidget#panel_tabs QTabBar::tab { background: transparent; border: 0px; padding: 8px 12px; color: $hint;
                                     font-size: 13px; }
QTabWidget#panel_tabs QTabBar::tab:selected { color: $ink; font-weight: 600; border-bottom: 2px solid $accent; }
QFrame#run_footer { background: $bar_light; border-top: 1px solid $separator; }
QLabel[role="dot"] { background: $disabled; border-radius: 4px; }
QLabel[role="dot"][state="ok"] { background: $ok; }
QLabel[role="dot"][state="busy"] { background: $fire; }
QPushButton#jog { font-size:22px; font-weight:bold; }
QPushButton#corner { font-size:17px; }
QGroupBox { font-weight:bold; }
QToolBar#main_toolbar { spacing: 0px; padding: 1px; }
QToolBar#main_toolbar QToolButton { padding: 2px 4px; font-size: 11px; min-width: 52px; }
QToolBar#main_toolbar QToolButton[role="icon"] { min-width: 0px; padding: 0px; }
QLineEdit#layer_name { background: transparent; }
QLineEdit#layer_name:focus { background: palette(base); }
QToolBar#tool_strip { padding: 2px 4px 2px 2px; spacing: 2px; }
QLabel#bed_warning { color: $error; font-weight: bold; padding: 2px 0; }
QFrame#update_bar { background: $update_bg; border-bottom: 1px solid $update_border; }
QLabel#node_hint { color: $hint; }
QWidget#top_bar { background: $bar_light; border-bottom: 1px solid $top_border; }
QToolBar#options_toolbar { padding: 0px; spacing: 0px; border: 0px; }
QScrollArea#top_bar_scroll, QScrollArea#top_bar_scroll > QWidget > QWidget { background: transparent; }
QLabel#tool_options_title { font-weight: bold; }
QLabel#ribbon_caption { color: $caption; font-size: 10px; padding-bottom: 1px; }
QFrame#ribbon_separator { color: $separator; margin: 4px 0px; }
QGroupBox QLabel, QGroupBox QCheckBox { font-weight:normal; }
QStatusBar[error="true"] { color: $error; }

/* the dialog pattern (kerfly/gui/widgets.py): a body, a footer with Cancel and the named action,
   sections, a preview bar */
QFrame#dialog_body { background: $panel; }
QFrame#dialog_body QScrollArea, QFrame#dialog_body QWidget#qt_scrollarea_viewport,
QFrame#dialog_body QWidget#qt_scrollarea_viewport > QWidget { background: transparent; }
QFrame#dialog_footer { background: $top_bar; border-top: 1px solid $separator; }
QFrame#preview_bar { background: $bar_light; border-bottom: 1px solid $separator; }
QPushButton[role="primary"], QPushButton[role="danger"], QPushButton[role="secondary"] {
    border-radius: ${radius}px; padding: 0px 12px; }
QPushButton[role="secondary"] { background: $panel; border: 1px solid $field_border; }
QPushButton[role="secondary"]:hover { background: $top_bar; }
QPushButton[role="primary"] { background: $primary; border: 1px solid $primary; color: $action_ink; font-weight: 600; }
QPushButton[role="primary"]:hover { background: $primary_hover; border-color: $primary_hover; }
QPushButton[role="danger"] { background: $danger; border: 1px solid $danger; color: $action_ink; font-weight: 600; }
QPushButton[role="primary"]:disabled, QPushButton[role="danger"]:disabled {
    background: $start_off; border-color: $start_off; }
QToolButton[role="segment"] { background: $panel; border: 1px solid $field_border; padding: 0px 10px; }
QTabWidget#preview_tabs::pane { border: 1px solid $separator; }
QTabWidget#preview_tabs QTabBar::tab { background: $panel; border: 1px solid $field_border; padding: 4px 12px;
                                       margin: 6px 0px; }
QTabWidget#preview_tabs QTabBar::tab:selected { background: $on_bg; color: $on_ink; font-weight: 600; }
QToolButton[role="segment"]:checked { background: $on_bg; color: $on_ink; font-weight: 600; }

/* roles (kerfly/gui/widgets.py) */
QLabel[role="hint"] { color: $hint; }
QLabel[role="caption"] { color: $caption; font-size: 10px; }
QLabel[role="error"] { color: $error; }
QLabel[role="section"] { font-weight: 600; }
QLabel[role="beta"] { color: $caption; font-size: 10px; border: 1px solid $separator; border-radius: 3px;
                      padding: 0px 4px; }
QFrame[role="warning"] { background: $warn_bg; border: 1px solid $warn_border; border-radius: ${radius}px; }
QFrame[role="warning"] QLabel { color: $warn_ink; }
QFrame[role="divider"] { color: $divider; }
QToolButton[role="icon"] { border: 1px solid transparent; border-radius: ${radius}px; padding: 0px; }
QToolButton[role="icon"]:hover { background: $hover; border-color: $separator; }
QToolButton[role="icon"]:checked { background: $on_bg; border-color: $on_border; }
QToolButton[role="swatch"] { border: 1px solid $swatch_border; border-radius: 3px; }
""")

_current = "light"


def system_is_dark():
    """The desktop's colour scheme (Qt 6.5+: Windows, macOS, GNOME, KDE)."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def resolve(name):
    """'light' or 'dark' for a setting value."""
    if name == "system":
        return "dark" if system_is_dark() else "light"
    return name if name in TOKENS else DEFAULT


def current():
    """The theme in use: 'light' or 'dark'."""
    return _current


def token(key):
    return TOKENS[_current][key]


def canvas(key):
    """A colour drawn on the bed or a preview, as a QColor."""
    from PySide6.QtGui import QColor
    return QColor(CANVAS[key])


def style_sheet(resolved=None):
    return STYLE.substitute(TOKENS[resolved or _current], radius=RADIUS)


def make_style():
    """Fusion, with the dialogs' buttons in one order on every system: Cancel first, then the named action
    on the right (GNOME's order), and no icons on them (the mockups show none)."""
    from PySide6.QtWidgets import QDialogButtonBox, QProxyStyle, QStyle, QStyleFactory

    class KerflyStyle(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, data=None):
            if hint == QStyle.SH_DialogButtonLayout:
                return QDialogButtonBox.GnomeLayout.value
            if hint == QStyle.SH_DialogButtonBox_ButtonsHaveIcons:
                return 0
            return super().styleHint(hint, option, widget, data)

    return KerflyStyle(QStyleFactory.create("Fusion"))


def light_palette(app):
    """Fusion's light palette with the window's own surfaces and the accent colour."""
    from PySide6.QtGui import QColor, QPalette
    pal = app.style().standardPalette()
    t = TOKENS["light"]
    for role, key in ((QPalette.Window, "window"), (QPalette.Base, "panel"), (QPalette.AlternateBase, "bar_light"),
                      (QPalette.Highlight, "accent"), (QPalette.Link, "accent"), (QPalette.WindowText, "ink"),
                      (QPalette.Text, "ink"), (QPalette.ButtonText, "ink")):
        pal.setColor(QPalette.Active, role, QColor(t[key]))
        pal.setColor(QPalette.Inactive, role, QColor(t[key]))
    pal.setColor(QPalette.Disabled, QPalette.Window, QColor(t["window"]))
    return pal


def dark_palette():
    from PySide6.QtGui import QColor, QPalette
    pal = QPalette()
    colors = {
        QPalette.Window: "#30343a", QPalette.WindowText: "#e3e6ea", QPalette.Base: "#24272b",
        QPalette.AlternateBase: "#2b2f34", QPalette.ToolTipBase: "#3a3f46", QPalette.ToolTipText: "#e3e6ea",
        QPalette.PlaceholderText: "#8a9099", QPalette.Text: "#e3e6ea", QPalette.Button: "#383d44",
        QPalette.ButtonText: "#e3e6ea", QPalette.BrightText: "#ff6e6e", QPalette.Link: "#64b5f6",
        QPalette.LinkVisited: "#b39ddb", QPalette.Highlight: "#2f6aa8", QPalette.HighlightedText: "#ffffff",
        QPalette.Light: "#4a5058", QPalette.Midlight: "#40454c", QPalette.Mid: "#2a2d32",
        QPalette.Dark: "#1e2024", QPalette.Shadow: "#141518",
    }
    for role, color in colors.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor("#7a8089"))
    pal.setColor(QPalette.Disabled, QPalette.Base, QColor("#2a2d31"))
    pal.setColor(QPalette.Disabled, QPalette.Button, QColor("#33373d"))
    return pal


def apply(app, name):
    """Fusion style with the light or the dark palette, the style sheet and the icon colour.
    Call before the window is built (icons are drawn when it is)."""
    global _current
    from kerfly.gui import icons
    _current = resolve(name)
    app.setStyle(make_style())
    if _current == "dark":
        app.setPalette(dark_palette())
    else:
        app.setPalette(light_palette(app))
    icons.set_ink(TOKENS[_current]["ink"], TOKENS[_current]["arrow"])
    app.setStyleSheet(style_sheet())
    return _current
