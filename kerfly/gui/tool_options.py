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

OPERATION_NAMES = [("cut", N_("Cut")), ("engrave", N_("Engrave outline")), ("hatch", N_("Hatch (lines)")),
                   ("fill", N_("Fill (raster)"))]
KIND_NAMES = {"rectangle": N_("Rectangle"), "ellipse": N_("Ellipse"), "polygon": N_("Polygon"),
              "line": N_("Line"), "polyline": N_("Polyline"), "path": N_("Path"), "pen": N_("Path"), "freehand": N_("Freehand"),
              "text": N_("Text")}
NEW_KIND_TITLES = {"rectangle": N_("New rectangle"), "ellipse": N_("New ellipse"),
                   "polygon": N_("New polygon"), "line": N_("New line"),
                   "polyline": N_("New polyline"), "pen": N_("New path"),
                   "freehand": N_("New freehand line"), "text": N_("New text")}


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


NODE_ACTIONS = [("insert", N_("Insert"), "I", N_("Insert a node after the selected one")),
                ("delete", N_("Delete"), "D", N_("Delete the selected nodes")),
                ("line", N_("Line"), "L", N_("Make the sides of the selected nodes straight lines")),
                ("curve", N_("Curve"), "C", N_("Make the sides of the selected nodes curves")),
                ("smooth", N_("Smooth"), "O", N_("Smooth curve through the selected nodes")),
                ("symmetric", N_("Symmetric"), "S", N_("Smooth with handles of equal length")),
                ("close", N_("Close / open"), "Z", N_("Close an open path, or open a closed one")),
                ("break", N_("Break"), "B", N_("Cut the path open at the selected node"))]


class ToolOptionsBar(QWidget):
    """Emits changed(spec) with an edited copy of the shown ShapeSpec, and
    node_action(code) from the node tool's buttons."""
    changed = Signal(object)
    node_action = Signal(str)

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

    def add_node_actions(self):
        """Buttons of the node tool (they act on the selected nodes)."""
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(2)
        for n, (code, label, key, tip) in enumerate(NODE_ACTIONS):
            b = QToolButton()
            b.setText(_(label))
            b.setToolTip("%s (%s)" % (_(tip), key))
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setAutoRaise(False)
            b.clicked.connect(lambda _c=False, c=code: self.node_action.emit(c))
            g.addWidget(b, n // 4, n % 4)
        self._add(box, _("Nodes"))

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
            if key in ("fill", "hatch") and not self.spec.closed:
                continue
            op.addItem(_(name), key)
        op.setCurrentIndex(max(0, op.findData(self.spec.operation)))
        op.setToolTip(_("Operation"))
        op.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        op.currentIndexChanged.connect(lambda _i: self._set("operation", op.currentData()))
        self._add(op, title)

        if self.spec.operation == "cut" and self.spec.closed:
            tb = QWidget()
            tg = QGridLayout(tb)
            tg.setContentsMargins(0, 0, 0, 0)
            tg.setVerticalSpacing(4)
            count = QSpinBox()
            count.setRange(0, 50)
            count.setValue(int(self.spec.tabs))
            count.setSpecialValueText(_("none"))
            count.setKeyboardTracking(False)
            count.setToolTip(_("Bridges per outline: short uncut gaps that hold the part in the sheet"))
            count.valueChanged.connect(lambda v: self._set("tabs", v))
            width = self._dspin("tab_width", 0.1, 20.0, " mm", decimals=1)
            width.setToolTip(_("Width of each bridge"))
            tg.addWidget(count, 0, 0)
            tg.addWidget(width, 1, 0)
            self._add(tb, _("Bridges"))

        if self.spec.operation == "hatch" and self.spec.closed:
            hb = QWidget()
            hg = QGridLayout(hb)
            hg.setContentsMargins(0, 0, 0, 0)
            hg.setHorizontalSpacing(4)
            hg.setVerticalSpacing(4)
            spacing = self._dspin("hatch_spacing", 0.05, 20.0, " mm", decimals=2)
            spacing.setSingleStep(0.1)
            spacing.setToolTip(_("Distance between the lines"))
            angle = self._dspin("hatch_angle", -180.0, 180.0, "\u00b0")
            angle.setSingleStep(15.0)
            angle.setToolTip(_("Direction of the lines"))
            cross = QToolButton()
            cross.setText("#")
            cross.setCheckable(True)
            cross.setChecked(self.spec.hatch_cross)
            cross.setToolTip(_("Cross-hatch: a second set of lines at 90\u00b0"))
            cross.toggled.connect(lambda on: self._set("hatch_cross", on))
            hg.addWidget(spacing, 0, 0)
            hg.addWidget(angle, 1, 0)
            hg.addWidget(cross, 0, 1, 2, 1)
            self._add(hb, _("Hatch"))

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

    def _dspin(self, attr, lo, hi, suffix, decimals=1):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
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
