"""
Options bar above the bed view: settings of the selected shape, or of the
drawing tool in use (like LightBurn's tool options bar), laid out as ribbon
sections with captions and separators.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFontComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from kerfly.gui import icons
from kerfly.gui.sizing import chars_width
from kerfly.i18n import N_, _

OPERATION_NAMES = [("cut", N_("Cut")), ("engrave", N_("Engrave outline")), ("fill", N_("Fill (raster)"))]
KIND_NAMES = {"rectangle": N_("Rectangle"), "ellipse": N_("Ellipse"), "polygon": N_("Polygon"),
              "line": N_("Line"), "polyline": N_("Polyline"), "text": N_("Text")}
NEW_KIND_TITLES = {"rectangle": N_("New rectangle"), "ellipse": N_("New ellipse"),
                   "polygon": N_("New polygon"), "line": N_("New line"),
                   "polyline": N_("New polyline"), "text": N_("New text")}


def ribbon_section(content, caption):
    """A ribbon section: content (widget or layout) with a small caption under it."""
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(2, 0, 2, 0)
    v.setSpacing(2)
    if isinstance(content, QWidget):
        v.addWidget(content, 0, Qt.AlignTop)
    else:
        v.addLayout(content)
    v.addStretch(1)
    label = QLabel(caption)
    label.setObjectName("ribbon_caption")
    label.setAlignment(Qt.AlignHCenter)
    v.addWidget(label)
    return box


def ribbon_separator():
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setObjectName("ribbon_separator")
    return line


class ToolOptionsBar(QWidget):
    """Emits changed(spec) with an edited copy of the shown ShapeSpec."""
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tool_options")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(4)
        self.spec = None
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.setInterval(400)       # rebuild text outlines after typing pauses
        self._text_timer.timeout.connect(self._emit)
        self.show_hint()

    # ---- building -------------------------------------------------------
    def _clear(self):
        self._text_timer.stop()
        while self.row.count():
            item = self.row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()                 # gone now, not only when Qt deletes it later
                w.setParent(None)
                w.deleteLater()

    def show_hint(self):
        """Nothing to edit: leave the bar empty (a hint text made the bar taller in narrow windows)."""
        self.spec = None
        self._clear()

    def _add(self, content, caption):
        if self.row.count():
            self.row.addWidget(ribbon_separator())
        self.row.addWidget(ribbon_section(content, caption))

    def show_spec(self, spec, title):
        """Show the options of spec (a ShapeSpec); title names what is edited."""
        self.spec = spec.copy()
        self._clear()

        op = QComboBox()
        for key, name in OPERATION_NAMES:
            if key == "fill" and not self.spec.closed:
                continue
            op.addItem(_(name), key)
        op.setCurrentIndex(max(0, op.findData(self.spec.operation)))
        op.setToolTip(_("Operation"))
        op.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        op.currentIndexChanged.connect(lambda _i: self._set("operation", op.currentData()))
        self._add(op, title)

        kind = self.spec.kind
        if kind == "rectangle":
            self._add(self._dspin("corner_radius", 0.0, 1000.0, " mm"), _("Corner radius"))
        elif kind == "polygon":
            sides = QSpinBox()
            sides.setRange(3, 64)
            sides.setValue(self.spec.sides)
            sides.setKeyboardTracking(False)
            sides.valueChanged.connect(lambda v: self._set("sides", v))
            self._add(sides, _("Sides"))
        elif kind == "text":
            text = QPlainTextEdit(self.spec.text)
            text.setPlaceholderText(_("Text"))
            text.setToolTip(_("Text; press Enter for a new line"))
            fm = text.fontMetrics()
            text.setFixedSize(chars_width(text, 16), fm.lineSpacing() * 2 + 14)
            text.setTabChangesFocus(True)
            text.textChanged.connect(lambda: self._text_edited(text.toPlainText()))
            self._add(text, _("Content"))

            font_box = QWidget()
            g = QGridLayout(font_box)
            g.setContentsMargins(0, 0, 0, 0)
            g.setHorizontalSpacing(2)
            g.setVerticalSpacing(4)
            font = QFontComboBox()
            font.setCurrentFont(QFont(self.spec.font_family))
            font.setFixedWidth(chars_width(font, 16) + 28)
            font.setToolTip(_("Font"))
            font.currentFontChanged.connect(lambda f: self._set("font_family", f.family()))
            g.addWidget(font, 0, 0, 1, 3)
            g.addWidget(self._dspin("font_size", 0.5, 500.0, " mm"), 1, 0)
            for i, (attr, icon, tip) in enumerate((("bold", "bold", N_("Bold")),
                                                   ("italic", "italic", N_("Italic")))):
                b = QToolButton()
                b.setIcon(icons.tabler(icon))
                b.setIconSize(QSize(18, 18))
                b.setCheckable(True)
                b.setChecked(getattr(self.spec, attr))
                b.setToolTip(_(tip))
                b.toggled.connect(lambda on, a=attr: self._set(a, on))
                g.addWidget(b, 1, 1 + i)
            self._add(font_box, _("Font"))
        self.row.addStretch(1)

    def _dspin(self, attr, lo, hi, suffix):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(1)
        w.setSuffix(suffix)
        w.setValue(getattr(self.spec, attr))
        w.setKeyboardTracking(False)
        if attr == "font_size":
            w.setToolTip(_("Text height"))
        w.valueChanged.connect(lambda v: self._set(attr, v))
        return w

    # ---- changes ----------------------------------------------------------
    def _set(self, attr, value):
        if self.spec is None:
            return
        setattr(self.spec, attr, value)
        self._emit()

    def _text_edited(self, text):
        if self.spec is not None and text != self.spec.text:
            self.spec.text = text
            self._text_timer.start()

    def _emit(self):
        if self.spec is not None:
            self.changed.emit(self.spec.copy())
