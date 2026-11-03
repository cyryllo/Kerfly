"""
Options bar above the bed view: settings of the selected shape, or of the
drawing tool in use (like LightBurn's tool options bar).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFontComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QSpinBox, QToolButton, QWidget)

from kerfly.gui import icons
from kerfly.i18n import N_, _

OPERATION_NAMES = [("cut", N_("Cut")), ("engrave", N_("Engrave outline")), ("fill", N_("Fill (raster)"))]
KIND_NAMES = {"rectangle": N_("Rectangle"), "ellipse": N_("Ellipse"), "polygon": N_("Polygon"),
              "line": N_("Line"), "text": N_("Text")}
# full phrases (adjectives agree with the noun in many languages)
NEW_KIND_TITLES = {"rectangle": N_("New rectangle:"), "ellipse": N_("New ellipse:"),
                   "polygon": N_("New polygon:"), "line": N_("New line:"), "text": N_("New text:")}


class ToolOptionsBar(QWidget):
    """Emits changed(spec) with an edited copy of the shown ShapeSpec."""
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tool_options")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(8, 4, 8, 4)
        self.layout_.setSpacing(4)
        self.spec = None
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.setInterval(350)       # rebuild text outlines after typing pauses
        self._text_timer.timeout.connect(self._emit)
        self.show_hint()

    # ---- building -------------------------------------------------------
    def _clear(self):
        self._text_timer.stop()
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()                 # gone now, not only when Qt deletes it later
                w.setParent(None)
                w.deleteLater()

    def show_hint(self):
        self.spec = None
        self._clear()
        label = QLabel(_("Choose a drawing tool on the right, or select a drawn shape, to see its options here."))
        label.setObjectName("tool_options_hint")
        self.layout_.addWidget(label)
        self.layout_.addStretch(1)

    def show_spec(self, spec, title):
        """Show the options of spec (a ShapeSpec); title says what is being edited."""
        self.spec = spec.copy()
        self._clear()
        caption = QLabel(title)
        caption.setObjectName("tool_options_title")
        self.layout_.addWidget(caption)

        op = QComboBox()
        for key, name in OPERATION_NAMES:
            if key == "fill" and not self.spec.closed:
                continue
            op.addItem(_(name), key)
        op.setCurrentIndex(max(0, op.findData(self.spec.operation)))
        op.currentIndexChanged.connect(lambda _i: self._set("operation", op.currentData()))
        self.layout_.addWidget(QLabel(_("Operation:")))
        self.layout_.addWidget(op)

        kind = self.spec.kind
        if kind == "rectangle":
            self.layout_.addWidget(QLabel(_("Corner radius:")))
            self.layout_.addWidget(self._dspin("corner_radius", 0.0, 1000.0, " mm"))
        elif kind == "polygon":
            self.layout_.addWidget(QLabel(_("Sides:")))
            sides = QSpinBox()
            sides.setRange(3, 64)
            sides.setValue(self.spec.sides)
            sides.setKeyboardTracking(False)
            sides.valueChanged.connect(lambda v: self._set("sides", v))
            self.layout_.addWidget(sides)
        elif kind == "text":
            text = QLineEdit(self.spec.text)
            text.setMinimumWidth(110)
            text.setPlaceholderText(_("Text"))
            text.textEdited.connect(self._text_edited)
            self.layout_.addWidget(text)
            font = QFontComboBox()
            font.setCurrentFont(QFont(self.spec.font_family))
            font.setMaximumWidth(150)
            font.currentFontChanged.connect(lambda f: self._set("font_family", f.family()))
            self.layout_.addWidget(font)
            self.layout_.addWidget(QLabel(_("Height:")))
            self.layout_.addWidget(self._dspin("font_size", 0.5, 500.0, " mm"))
            for attr, icon, tip in (("bold", "bold", N_("Bold")), ("italic", "italic", N_("Italic"))):
                b = QToolButton()
                b.setIcon(icons.tabler(icon))
                b.setIconSize(QSize(18, 18))
                b.setCheckable(True)
                b.setChecked(getattr(self.spec, attr))
                b.setToolTip(_(tip))
                b.toggled.connect(lambda on, a=attr: self._set(a, on))
                self.layout_.addWidget(b)
        self.layout_.addStretch(1)

    def _dspin(self, attr, lo, hi, suffix):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(1)
        w.setSuffix(suffix)
        w.setValue(getattr(self.spec, attr))
        w.setKeyboardTracking(False)
        w.valueChanged.connect(lambda v: self._set(attr, v))
        return w

    # ---- changes ----------------------------------------------------------
    def _set(self, attr, value):
        if self.spec is None:
            return
        setattr(self.spec, attr, value)
        self._emit()

    def _text_edited(self, text):
        if self.spec is not None:
            self.spec.text = text
            self._text_timer.start()

    def _emit(self):
        if self.spec is not None:
            self.changed.emit(self.spec.copy())
