"""
Light and dark look of the window (Settings → View → Theme; applies after a
restart, like the language). The laser bed itself stays light in both: it
stands for the material, and designs are drawn on it in their real colours.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from string import Template

from kerfly.i18n import N_

# (setting value, name shown in Settings)
THEMES = [("light", N_("Light")), ("dark", N_("Dark")), ("system", N_("As the system"))]
DEFAULT = "light"

TOKENS = {
    "light": {"top_bar": "#eef0f3", "top_border": "#c4c9d0", "update_bg": "#e3f2fd", "update_border": "#90caf9",
              "hint": "#4b5563", "caption": "#6b7280", "separator": "#c4c9d0", "ink": "#2b2f36",
              "arrow": "#202124", "swatch_border": "#555555", "ok": "#2e7d32", "error": "#c62828",
              "start_off": "#9e9e9e", "stop_off": "#bdbdbd"},
    "dark": {"top_bar": "#2b2f35", "top_border": "#1b1e22", "update_bg": "#1d3a5c", "update_border": "#2f6aa8",
             "hint": "#b4bac3", "caption": "#9aa1ab", "separator": "#4a505a", "ink": "#d9dce1",
             "arrow": "#e3e6ea", "swatch_border": "#9aa1ab", "ok": "#66bb6a", "error": "#ef5350",
             "start_off": "#4a4f56", "stop_off": "#4a4f56"},
}

STYLE = Template("""
QPushButton#start { background:#2e7d32; color:white; font-weight:bold; border-radius:4px; }
QPushButton#start:disabled { background:$start_off; }
QPushButton#stop { background:#c62828; color:white; font-weight:bold; border-radius:4px; }
QPushButton#stop:disabled { background:$stop_off; }
QPushButton#start, QPushButton#stop { font-size: 14px; }
QPushButton#jog { font-size:22px; font-weight:bold; }
QPushButton#corner { font-size:17px; }
QGroupBox { font-weight:bold; }
QToolBar#main_toolbar { spacing: 0px; padding: 1px; }
QToolBar#main_toolbar QToolButton { padding: 2px 0px; font-size: 11px; min-width: 34px; }
QLineEdit#layer_name { background: transparent; }
QLineEdit#layer_name:focus { background: palette(base); }
QToolBar#tool_strip { padding: 2px 4px 2px 2px; spacing: 2px; }
QLabel#bed_warning { color: $error; font-weight: bold; padding: 2px 0; }
QFrame#update_bar { background: $update_bg; border-bottom: 1px solid $update_border; }
QLabel#node_hint { color: $hint; }
QWidget#top_bar { background: $top_bar; border-bottom: 1px solid $top_border; }
QLabel#tool_options_title { font-weight: bold; }
QLabel#ribbon_caption { color: $caption; font-size: 10px; padding-bottom: 1px; }
QFrame#ribbon_separator { color: $separator; margin: 4px 0px; }
QGroupBox QLabel, QGroupBox QCheckBox { font-weight:normal; }
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


def style_sheet(resolved=None):
    return STYLE.substitute(TOKENS[resolved or _current])


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
    app.setStyle("Fusion")
    if _current == "dark":
        app.setPalette(dark_palette())
    else:
        app.setPalette(app.style().standardPalette())
    icons.set_ink(TOKENS[_current]["ink"], TOKENS[_current]["arrow"])
    app.setStyleSheet(style_sheet())
    return _current
