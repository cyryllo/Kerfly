"""
Small building blocks shared by the window and the dialogs, so each of them
looks and behaves the same everywhere: a field's caption with its icon, an
icon button, a hint, a section title, a "beta" badge, a separator.

Their look comes from theme.py: sizes from its constants, colours from the
style sheet through the widget's "role" property (no colour is set here).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from kerfly.gui import icons, theme
from kerfly.i18n import _


def set_role(widget, role):
    """Give a widget a role of the style sheet (hint, error, caption, section, beta, warning, icon, …)
    and let the style sheet look at it again."""
    widget.setProperty("role", role)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    return widget


def icon_pixmap_label(icon, tip="", size=None):
    """A label showing a Tabler icon (name) or a QIcon, with a tooltip."""
    label = QLabel()
    size = size or theme.ICON
    pic = icons.tabler(icon) if isinstance(icon, str) else icon
    label.setPixmap(pic.pixmap(size, size))
    if tip:
        label.setToolTip(tip)
    return label


def caption(icon, text, tip):
    """A form caption with its icon in front, both with the tooltip (every field says what it is with an
    icon and a tooltip, not with a caption alone)."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(theme.SPACE_S)
    label = QLabel(text)
    for w in (box, label):
        w.setToolTip(tip)
    row.addWidget(icon_pixmap_label(icon, tip))
    row.addWidget(label, 1)
    return box


def with_icon(icon, field, tip=None):
    """A field with its icon in front (both with the field's tooltip)."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(theme.SPACE_S)
    row.addWidget(icon_pixmap_label(icon, tip or field.toolTip()))
    row.addWidget(field)
    return box


def icon_button(icon=None, tip="", action=None, checkable=False, size=None, icon_size=None):
    """A square icon-only button (HEIGHT_FIELD, ICON); from an action when one is given."""
    b = QToolButton()
    if action is not None:
        b.setDefaultAction(action)
    else:
        if icon is not None:
            b.setIcon(icons.tabler(icon) if isinstance(icon, str) else icon)
        if tip:
            b.setToolTip(tip)
        b.setCheckable(checkable)
    size = size or theme.HEIGHT_FIELD
    icon_size = icon_size or theme.ICON
    b.setIconSize(QSize(icon_size, icon_size))
    b.setFixedSize(size, size)
    b.setToolButtonStyle(Qt.ToolButtonIconOnly)
    b.setAutoRaise(True)
    set_role(b, "icon")
    return b


def label(text, role="hint", wrap=True):
    """A label of a role: "hint" (grey explanation), "error" (red), "caption" (small grey), "section"
    (a section's bold title)."""
    w = QLabel(text)
    w.setWordWrap(wrap)
    return set_role(w, role)


def hint(text, wrap=True):
    return label(text, "hint", wrap)


def error(text, wrap=True):
    return label(text, "error", wrap)


def section_title(text):
    return label(text, "section", wrap=False)


def beta_badge(tip=None):
    """The small "beta" mark next to a feature not yet confirmed on a laser."""
    w = QLabel(_("beta"))
    w.setToolTip(tip or _("New: not yet confirmed on a real laser. Please report how it works."))
    w.setAlignment(Qt.AlignCenter)
    return set_role(w, "beta")


def separator(vertical=True):
    """A thin line between groups of controls."""
    line = QFrame()
    line.setFrameShape(QFrame.VLine if vertical else QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    return set_role(line, "divider")
