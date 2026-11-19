"""
Small building blocks shared by the window and the dialogs, so each of them
looks and behaves the same everywhere: a field's caption with its icon, an
icon button, a hint, a section title, a "beta" badge, a separator.

The dialog pattern (every dialog is built of these):

- DialogBody: the light area with the content (PAD_DIALOG inside);
- Section: a bold title over a form of captions (icon, text, tooltip) on the
  left and fields on the right; a feature not yet confirmed on a laser gets a
  "beta" badge by its caption;
- PreviewBar: the 44 px bar over a preview, with its view switches;
- DialogFooter: an information on the left, then Cancel and the action named
  for what it does ("Nest", "Save", "Delete laser"; never "OK") on the right;
  the buttons stay those of a QDialogButtonBox (keyboard, tests);
- dialog_layout(): puts them together without margins.

Their look comes from theme.py: sizes from its constants, colours from the
style sheet through the widget's "role" property (no colour is set here).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QRadioButton, QToolButton, QVBoxLayout, QWidget)

from kerfly.gui import icons, theme
from kerfly.i18n import _


def set_role(widget, role):
    """Give a widget a role of the style sheet (hint, error, caption, section, beta, warning, icon, …)
    and let the style sheet look at it again."""
    if widget.property("role") == role:
        return widget
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


def status_dot(state=""):
    """A small round dot saying a state: "" grey (not connected), "ok" green, "busy" orange."""
    dot = QLabel()
    dot.setFixedSize(theme.SPACE_M, theme.SPACE_M)
    set_role(dot, "dot")
    set_dot(dot, state)
    return dot


def set_dot(dot, state):
    if dot.property("state") != state:
        dot.setProperty("state", state)
        dot.style().unpolish(dot)
        dot.style().polish(dot)


def separator(vertical=True):
    """A thin line between groups of controls."""
    line = QFrame()
    line.setFrameShape(QFrame.VLine if vertical else QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    return set_role(line, "divider")


def beta_caption(widget):
    """A caption (or a check box) with the beta badge after it."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(theme.SPACE_M)
    row.addWidget(widget)
    row.addWidget(beta_badge())
    row.addStretch(1)
    return box


# ---- the dialog pattern -----------------------------------------------------------------------------

class DialogBody(QFrame):
    """The light area of a dialog with its content; .layout() is a QVBoxLayout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dialog_body")
        v = QVBoxLayout(self)
        v.setContentsMargins(theme.PAD_DIALOG, theme.PAD_DIALOG, theme.PAD_DIALOG, theme.PAD_DIALOG)
        v.setSpacing(theme.SPACE_L)

    def add(self, widget, stretch=0):
        self.layout().addWidget(widget, stretch)
        return widget


class Section(QWidget):
    """A section of a form: a bold title, then rows of a caption (left) and a field (right)."""

    def __init__(self, title=None, beta=False, parent=None):
        """beta: the badge by the title (the whole section is new)."""
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.SPACE_ROW)
        self.title = None
        if title:
            self.title = section_title(title)
            v.addWidget(beta_caption(self.title) if beta else self.title)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(theme.SPACE_L)
        self.grid.setVerticalSpacing(theme.SPACE_ROW)
        self.grid.setColumnStretch(0, 1)
        v.addLayout(self.grid)

    def add_row(self, icon, text, tip, field, beta=False):
        """A field with its caption (icon, text, both with the tooltip)."""
        cap = caption(icon, text, tip)
        if beta:
            cap.layout().insertWidget(2, beta_badge())
        if not field.toolTip():
            field.setToolTip(tip)
        r = self.grid.rowCount()
        self.grid.addWidget(cap, r, 0)
        self.grid.addWidget(field, r, 1)
        return field

    def add_wide(self, widget, beta=False):
        """A widget across both columns (a check box with its own text, a hint)."""
        self.grid.addWidget(beta_caption(widget) if beta else widget, self.grid.rowCount(), 0, 1, 2)
        return widget


class PreviewBar(QFrame):
    """The bar over a preview (HEIGHT_ACTION): view switches on the left, more on the right after a stretch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("preview_bar")
        self.setFixedHeight(theme.HEIGHT_ACTION)
        row = QHBoxLayout(self)
        row.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_L, 0)
        row.setSpacing(theme.SPACE_L)

    def add(self, widget):
        self.layout().addWidget(widget)
        return widget

    def add_separator(self):
        self.layout().addWidget(separator())

    def add_stretch(self):
        self.layout().addStretch(1)


class Segmented(QWidget):
    """Buttons of which one is on (Parts | 3D); toggled(key) when another is chosen."""
    toggled = Signal(str)

    def __init__(self, options, current=None, parent=None):
        """options: [(key, text, tooltip)]."""
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, text, tip in options:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setFixedHeight(theme.HEIGHT_FIELD - 2)
            set_role(b, "segment")
            self.group.addButton(b)
            self.buttons[key] = b
            row.addWidget(b)
            b.toggled.connect(lambda on, k=key: on and self.toggled.emit(k))
        self.set_current(current or options[0][0])

    def current(self):
        return next(k for k, b in self.buttons.items() if b.isChecked())

    def set_current(self, key):
        self.buttons[key].setChecked(True)


class CornerPicker(QFrame):
    """A picture of the laser's bed with a radio button in each corner (the home corner of a laser); one is
    chosen. changed(key) when another is chosen. Keys: "UL", "UR", "LL", "LR"; corners not in `allowed` are
    greyed out with `blocked_tip` as their tooltip."""
    changed = Signal(str)
    CORNERS = (("UL", 0, 0, Qt.AlignLeft | Qt.AlignTop), ("UR", 0, 1, Qt.AlignRight | Qt.AlignTop),
               ("LL", 1, 0, Qt.AlignLeft | Qt.AlignBottom), ("LR", 1, 1, Qt.AlignRight | Qt.AlignBottom))

    def __init__(self, current="UL", allowed=None, tips=None, blocked_tip="", parent=None):
        super().__init__(parent)
        set_role(self, "corner_picker")
        self.setFixedSize(*theme.CORNER_PICKER)
        grid = QGridLayout(self)
        grid.setContentsMargins(theme.SPACE_S, theme.SPACE_S, theme.SPACE_S, theme.SPACE_S)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, r, c, align in self.CORNERS:
            b = QRadioButton()
            on = allowed is None or key in allowed
            b.setEnabled(on)
            b.setToolTip((tips or {}).get(key, "") if on else blocked_tip)
            self.group.addButton(b)
            self.buttons[key] = b
            grid.addWidget(b, r, c, align)
            b.toggled.connect(lambda checked, k=key: checked and self.changed.emit(k))
        self.set_current(current)

    def current(self):
        return next((k for k, b in self.buttons.items() if b.isChecked()), "UL")

    def set_current(self, key):
        self.buttons.get(key, self.buttons["UL"]).setChecked(True)


class DialogFooter(QFrame):
    """The footer of a dialog: an information on the left (.info), then the buttons of a QDialogButtonBox
    (.box) in the style's order, Cancel first and the named action last."""

    PRIMARY = (QDialogButtonBox.Ok, QDialogButtonBox.Save, QDialogButtonBox.Apply, QDialogButtonBox.Yes,
               QDialogButtonBox.Open)

    def __init__(self, action=None, buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel, danger=False,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("dialog_footer")
        row = QHBoxLayout(self)
        row.setContentsMargins(theme.SPACE_L, theme.SPACE_L, theme.SPACE_L, theme.SPACE_L)
        row.setSpacing(theme.SPACE_M)
        self.info = label("", "hint", wrap=False)
        row.addWidget(self.info, 1)
        self.box = QDialogButtonBox(buttons)
        row.addWidget(self.box)
        self.primary = next((self.box.button(b) for b in self.PRIMARY if self.box.button(b) is not None), None)
        # Qt's own words for its buttons are not translated here: ours
        for which, text in ((QDialogButtonBox.Cancel, _("Cancel")), (QDialogButtonBox.Close, _("Close")),
                            (QDialogButtonBox.Save, _("Save"))):
            if self.box.button(which) is not None:
                self.box.button(which).setText(text)
        for b in self.box.buttons():
            self.style_button(b, "secondary")
        if self.primary is not None:
            if action:
                self.primary.setText(action)
            self.style_button(self.primary, "danger" if danger else "primary")

    @staticmethod
    def style_button(button, role):
        button.setMinimumWidth(theme.BUTTON_MIN_WIDTH)
        button.setFixedHeight(theme.HEIGHT_BUTTON)
        set_role(button, role)

    def add_button(self, text, role=QDialogButtonBox.ActionRole, tip=""):
        """One more button (e.g. "Defaults"); the style puts it by its role."""
        b = self.box.addButton(text, role)
        if tip:
            b.setToolTip(tip)
        self.style_button(b, "secondary")
        return b

    def connect(self, dialog):
        self.box.accepted.connect(dialog.accept)
        self.box.rejected.connect(dialog.reject)


def dialog_layout(dialog, body, footer, preview_bar=None):
    """A dialog's layout: [preview bar,] body, footer, edge to edge."""
    v = QVBoxLayout(dialog)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    if preview_bar is not None:
        v.addWidget(preview_bar)
    v.addWidget(body, 1)
    v.addWidget(footer)
    if footer.primary is not None:
        footer.primary.setDefault(True)          # Enter: the action (only once the button is in the dialog)
    return v


def ask(parent, title, text, buttons=None, default=None, names=None, primary=None, danger=False):
    """A question (docs/ui-mockups/Message): its buttons named for what they do ("Delete laser", "Stop and
    quit"; No is "Cancel"), the action last in the primary colour (red for a deletion). The same arguments
    and answer (the standard button clicked) as QMessageBox.question, so the tests answer both alike."""
    from PySide6.QtWidgets import QMessageBox
    buttons = buttons if buttons is not None else QMessageBox.Yes | QMessageBox.No
    box = QMessageBox(QMessageBox.Question, title, text, buttons, parent)
    if default is not None:
        box.setDefaultButton(default)
    for button, name in [(QMessageBox.No, _("Cancel"))] + list((names or {}).items()):
        b = box.button(button)
        if b is not None:
            b.setText(name)
    primary = primary if primary is not None else QMessageBox.Yes
    if box.button(primary) is not None:
        DialogFooter.style_button(box.button(primary), "danger" if danger else "primary")
    box.exec()
    clicked = box.clickedButton()
    return box.standardButton(clicked) if clicked is not None else QMessageBox.NoButton
