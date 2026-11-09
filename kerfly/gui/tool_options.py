"""
Options bar above the bed view: settings of the selected shape, or of the
drawing tool in use (like LightBurn's tool options bar), laid out as ribbon
sections with captions and separators.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QSizePolicy, QComboBox, QDoubleSpinBox, QFontComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from kerfly.gui import icons
from kerfly.gui.sizing import chars_width
from kerfly.i18n import N_, _

OPERATION_NAMES = [("cut", N_("Cut")), ("engrave", N_("Engrave outline")), ("fill", N_("Fill (raster)"))]
KIND_NAMES = {"rectangle": N_("Rectangle"), "ellipse": N_("Ellipse"), "polygon": N_("Polygon"),
              "line": N_("Line"), "polyline": N_("Polyline"), "path": N_("Path"), "pen": N_("Path"), "freehand": N_("Freehand"),
              "text": N_("Text")}
# fill patterns (kerfly.core.patterns.PATTERNS), names for the GUI
PATTERN_NAMES = [("lines", N_("Lines")), ("cross", N_("Cross-hatch")), ("waves", N_("Waves")),
                 ("zigzag", N_("Zigzag")), ("circles", N_("Circles")), ("honeycomb", N_("Honeycomb")),
                 ("diamonds", N_("Diamonds")), ("bricks", N_("Bricks")), ("concentric", N_("Concentric"))]
# living hinges (kerfly.core.patterns.HINGES), names for the GUI
HINGE_NAMES = [("straight", N_("Straight cuts")), ("wave", N_("Wavy cuts")), ("zigzag", N_("Zigzag cuts"))]
NEW_KIND_TITLES = {"rectangle": N_("New rectangle"), "ellipse": N_("New ellipse"),
                   "polygon": N_("New polygon"), "line": N_("New line"),
                   "polyline": N_("New polyline"), "pen": N_("New path"),
                   "freehand": N_("New freehand line"), "text": N_("New text"),
                   "textpath": N_("New text on a path")}


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


# node tool buttons: (section, [(code, label, icon, key, tooltip, needs a selected node)])
NODE_SECTIONS = [
    (N_("Node"), [("insert", N_("Add"), "square-plus", "I",
                   N_("Add a node in the middle of the side after the selected node"), True),
                  ("delete", N_("Remove"), "square-minus", "D",
                   N_("Remove the selected nodes"), True)]),
    (N_("Side"), [("line", N_("Straight"), "slash", "L",
                   N_("Make the sides at the selected nodes straight lines"), True),
                  ("curve", N_("Curve"), "vector-spline", "C",
                   N_("Make the sides at the selected nodes curves with handles you can drag"), True)]),
    (N_("Curve through the node"), [
        ("smooth", N_("Smooth"), "wave-sine", "O",
         N_("No corner at the selected nodes: the curve passes smoothly through them"), True),
        ("symmetric", N_("Symmetric"), "arrows-horizontal", "S",
         N_("Smooth, with both handles of the same length"), True)]),
    (N_("Shape"), [("close", N_("Close / open"), "circle-dashed", "Z",
                    N_("Close an open shape, or open a closed one"), False),
                   ("break", N_("Cut open"), "scissors", "B",
                    N_("Cut the shape open at the selected node"), True)]),
]


class ToolOptionsBar(QWidget):
    """Emits changed(spec) with an edited copy of the shown ShapeSpec, and
    node_action(code) from the node tool's buttons."""
    changed = Signal(object)
    node_action = Signal(str)
    offset_changed = Signal(dict)       # the Offset tool's settings
    offset_apply = Signal()             # the Offset tool's "Offset selected" button

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
        self._node_buttons = []                  # their widgets are deleted below
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
        """Buttons of the node tool, in sections, with icons. Those that need a
        selected node are greyed out until a node is clicked."""
        self._node_buttons = []
        last = self.row.itemAt(self.row.count() - 1) if self.row.count() else None
        if last is not None and last.spacerItem() is not None:
            self.row.takeAt(self.row.count() - 1)     # the stretch goes after the node sections
        for section, actions in NODE_SECTIONS:
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            for code, label, icon, key, tip, needs_node in actions:
                b = QToolButton()
                b.setText(_(label))
                b.setIcon(icons.tabler(icon))
                b.setIconSize(QSize(18, 18))
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                b.setToolTip("%s (%s)" % (_(tip), key))
                b.setAutoRaise(True)
                b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                b.clicked.connect(lambda _c=False, c=code: self.node_action.emit(c))
                v.addWidget(b)
                self._node_buttons.append((b, needs_node))
            self._add(box, _(section))
        self.row.addStretch(1)                           # keep the sections together on the left
        self.set_node_selection(0)

    def set_node_selection(self, count):
        """Enable the node buttons that need a selected node, and say what to do."""
        for b, needs_node in getattr(self, "_node_buttons", []):
            try:
                b.setEnabled(count > 0 or not needs_node)
            except RuntimeError:
                pass                             # the bar was rebuilt meanwhile

    def _add(self, content, caption):
        if self.row.count():
            self.row.addWidget(ribbon_separator())
        self.row.addWidget(ribbon_section(content, caption))

    def show_spec(self, spec, title):
        """Show the options of spec (a ShapeSpec); title names what is edited."""
        self.spec = spec.copy()
        self._clear()

        # what the laser does with the shape is chosen with its layer (bar above, Layer)

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
            count.setProperty("spec_attr", "tabs")
            width = self._dspin("tab_width", 0.1, 20.0, " mm", decimals=1)
            width.setToolTip(_("Width of each bridge"))
            tg.addWidget(self._icon_label("hash", count.toolTip()), 0, 0)
            tg.addWidget(count, 0, 1)
            tg.addWidget(self._icon_label("arrows-horizontal", width.toolTip()), 1, 0)
            tg.addWidget(width, 1, 1)
            self._add(tb, _("Bridges"))

        if self.spec.operation in ("cut", "engrave") and self.spec.closed:
            self._add_fill_section()
            if self.spec.hinge_pattern:                  # added with the Living hinge tool
                self._add_hinge_section()


        kind = self.spec.kind
        if kind == "rectangle":
            radius = self._dspin("corner_radius", 0.0, 1000.0, " mm")
            radius.setToolTip(_("Corner radius: 0 for sharp corners"))
            self._add(self._with_icon("border-radius", radius), _("Corner radius"))
        elif kind == "polygon":
            sides = QSpinBox()
            sides.setRange(3, 64)
            sides.setValue(self.spec.sides)
            sides.setKeyboardTracking(False)
            sides.setToolTip(_("Number of sides of the regular polygon"))
            sides.valueChanged.connect(lambda v: self._set("sides", v))
            sides.setProperty("spec_attr", "sides")
            self._add(self._with_icon("hexagon", sides), _("Sides"))
        elif kind == "text":
            text = QPlainTextEdit(self.spec.text)
            text.setPlaceholderText(_("Text"))
            text.setToolTip(_("Text; press Enter for a new line"))
            fm = text.fontMetrics()
            text.setFixedSize(chars_width(text, 16), fm.lineSpacing() * 2 + 14)
            text.setTabChangesFocus(True)
            text.textChanged.connect(lambda: self._text_edited(text.toPlainText()))
            text.setProperty("spec_attr", "text")
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
            font.setProperty("spec_attr", "font_family")
            g.addWidget(font, 0, 0, 1, 4)
            spacing = self._dspin("text_spacing", -50.0, 200.0, " mm", decimals=2)
            spacing.setSingleStep(0.1)
            spacing.setToolTip(_("Letter spacing: space added between the letters (0: as the font sets it)"))
            g.addWidget(self._icon_label("letter-spacing", spacing.toolTip()), 0, 4)
            g.addWidget(spacing, 0, 5)
            size = self._dspin("font_size", 0.5, 500.0, " mm")
            g.addWidget(self._icon_label("text-size", size.toolTip()), 1, 0)
            g.addWidget(size, 1, 1)
            for i, (attr, icon, tip) in enumerate((("bold", "bold", N_("Bold")),
                                                   ("italic", "italic", N_("Italic")))):
                b = QToolButton()
                b.setIcon(icons.tabler(icon))
                b.setIconSize(QSize(18, 18))
                b.setCheckable(True)
                b.setChecked(getattr(self.spec, attr))
                b.setToolTip(_(tip))
                b.toggled.connect(lambda on, a=attr: self._set(a, on))
                b.setProperty("spec_attr", attr)
                g.addWidget(b, 1, 2 + i)
            self._add(font_box, _("Font"))
            if self.spec.text_path:
                pb = QWidget()
                pg = QGridLayout(pb)
                pg.setContentsMargins(0, 0, 0, 0)
                pg.setHorizontalSpacing(4)
                pg.setVerticalSpacing(4)
                offset = self._dspin("text_path_offset", -5000.0, 5000.0, " mm")
                offset.setSingleStep(1.0)
                offset.setToolTip(_("Position along the path: where the text starts (you can also drag the text "
                                    "with the mouse)"))
                flip = QToolButton()
                flip.setIcon(icons.tabler("flip-vertical"))
                flip.setIconSize(QSize(18, 18))
                flip.setCheckable(True)
                flip.setChecked(self.spec.text_path_flip)
                flip.setToolTip(_("Other side: the text runs the other way, on the other side of the line"))
                flip.toggled.connect(lambda v: self._set("text_path_flip", v))
                flip.setProperty("spec_attr", "text_path_flip")
                straight = QToolButton()
                straight.setText(_("Straight text"))
                straight.setToolTip(_("Take the text off the path: back to a straight line of text"))
                straight.clicked.connect(lambda: self._set("text_path", []))
                distance = self._dspin("text_path_distance", -500.0, 500.0, " mm")
                distance.setSingleStep(0.5)
                distance.setToolTip(_("Distance from the line: space between the line and the foot of the letters "
                                      "(minus: the letters cross the line)"))
                pg.addWidget(self._icon_label("route", offset.toolTip()), 0, 0)
                pg.addWidget(offset, 0, 1)
                pg.addWidget(flip, 0, 2)
                pg.addWidget(self._icon_label("line-height", distance.toolTip()), 1, 0)
                pg.addWidget(distance, 1, 1)
                pg.addWidget(straight, 1, 2)
                self._add(pb, _("Text on path"))
        self.row.addStretch(1)

    def show_fill_tool(self, spec):
        """Options of the Fill tool: the pattern given to the shapes it is clicked on."""
        self.spec = spec.copy()
        self._clear()
        self._add_fill_section(tool=True)       # what to do is said in the status bar
        self.row.addStretch(1)

    def show_offset_tool(self, values):
        """Options of the Offset tool: how far the new outline lies from the shape,
        its corners, keep the shape or replace it; a button for the selected shapes."""
        self.spec = None
        self._clear()
        self.offset_values = dict(values)
        g = QGridLayout()
        g.setHorizontalSpacing(4)
        g.setVerticalSpacing(2)
        distance = QDoubleSpinBox()
        distance.setRange(-50.0, 50.0)
        distance.setDecimals(2)
        distance.setSingleStep(0.5)
        distance.setSuffix(" mm")
        distance.setValue(float(values["offset_distance"]))
        distance.setKeyboardTracking(False)
        distance.setToolTip(_("Distance: how far the new outline lies from the shape, positive outside (holes "
                              "get smaller), negative inside"))
        distance.setProperty("spec_attr", "offset_distance")
        distance.valueChanged.connect(lambda v: self._set_offset("offset_distance", v))
        g.addWidget(self._icon_label("arrows-horizontal", distance.toolTip()), 0, 0)
        g.addWidget(distance, 0, 1)
        join = QComboBox()
        join.addItem(icons.tabler("border-radius"), _("Round"), "round")
        join.addItem(icons.tabler("square"), _("Sharp"), "miter")
        join.setCurrentIndex(max(0, join.findData(values["offset_join"])))
        join.setToolTip(_("Corners of the new outline: rounded, or sharp like the shape's"))
        join.setProperty("spec_attr", "offset_join")
        join.currentIndexChanged.connect(lambda _i: self._set_offset("offset_join", join.currentData()))
        g.addWidget(self._icon_label("border-radius", join.toolTip()), 1, 0)
        g.addWidget(join, 1, 1)
        keep = QToolButton()
        keep.setCheckable(True)
        keep.setChecked(bool(values["offset_keep"]))
        keep.setIcon(icons.tabler("copy"))
        keep.setText(_("Keep the original"))
        keep.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        keep.setToolTip(_("On: the new outline is added next to the shape; off: it replaces the shape"))
        keep.setProperty("spec_attr", "offset_keep")
        keep.toggled.connect(lambda on: self._set_offset("offset_keep", on))
        g.addWidget(keep, 0, 2)
        apply = QToolButton()
        apply.setIcon(icons.tabler("box-padding"))
        apply.setText(_("Offset selected"))
        apply.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        apply.setToolTip(_("Draw the new outline around the shapes selected now (or click a shape on the bed)"))
        apply.clicked.connect(self.offset_apply.emit)
        self.offset_apply_button = apply
        g.addWidget(apply, 1, 2)
        box = QWidget()
        box.setLayout(g)
        self.row.addWidget(ribbon_section(box, _("Offset")))
        self.row.addStretch(1)

    def _set_offset(self, key, value):
        self.offset_values[key] = value
        self.offset_changed.emit(dict(self.offset_values))

    def show_hinge_tool(self, spec):
        """Options of the Living hinge tool: the cuts given to the shapes it is clicked on."""
        self.spec = spec.copy()
        self._clear()
        self._add_hinge_section(tool=True)      # what to do is said in the status bar
        self.row.addStretch(1)

    def _add_hinge_section(self, tool=False):
        """Living hinge of a closed shape: pattern, cut length, bridge, row spacing,
        direction, solid border."""
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(4)
        g.setVerticalSpacing(4)
        pattern = QComboBox()
        pattern.setIconSize(QSize(22, 22))
        pattern.addItem(_("No hinge"), "")
        for code, name in HINGE_NAMES:
            pattern.addItem(icons.hinge_pattern_icon(code), _(name), code)
        pattern.setCurrentIndex(max(0, pattern.findData(self.spec.hinge_pattern)))
        pattern.setToolTip(_("Living hinge: rows of cuts that let the sheet bend across them"))
        pattern.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        # tool: every choice counts, also the one already shown (it may not be on the shapes yet)
        (pattern.activated if tool else pattern.currentIndexChanged).connect(
            lambda _i: self._set("hinge_pattern", pattern.currentData()))
        pattern.setProperty("spec_attr", "hinge_pattern")
        g.addWidget(pattern, 0, 0, 1, 4)
        if self.spec.hinge_pattern or tool:
            # (field, from, to, unit, icon, tooltip, row, column); two rows, like every section
            fields = (("hinge_cut", 1.0, 500.0, " mm", "ruler-measure", N_("Length of one cut"), 0, 4),
                      ("hinge_gap", 0.2, 50.0, " mm", "link",
                       N_("Bridge: uncut material between two cuts in a row"), 0, 6),
                      ("hinge_spacing", 0.2, 50.0, " mm", "line-height",
                       N_("Distance between the rows of cuts (smaller: bends more)"), 1, 0),
                      ("hinge_angle", -180.0, 180.0, "\u00b0", "rotate-2",
                       N_("Direction of the cuts (90\u00b0: up and down; the sheet bends across them)"), 1, 2),
                      ("hinge_margin", 0.0, 100.0, " mm", "circle-dashed",
                       N_("Solid border: no cuts this close to the outline"), 1, 4),
                      ("hinge_band", 0.0, 2000.0, " mm", "arrows-horizontal",
                       N_("Width of the hinge band, across the cuts (0: the whole shape)"), 0, 8),
                      ("hinge_band_offset", -2000.0, 2000.0, " mm", "focus-centered",
                       N_("Where the band is: its middle from the middle of the shape (minus: left / up, "
                          "plus: right / down)"), 1, 6))
            for attr, lo, hi, unit, icon, tip, row, col in fields:
                w = self._dspin(attr, lo, hi, unit)
                w.setSingleStep(90.0 if attr == "hinge_angle" else 0.5)
                w.setToolTip(_(tip))
                g.addWidget(self._icon_label(icon, _(tip)), row, col)
                g.addWidget(w, row, col + 1)
        self._add(box, _("Living hinge"))

    def _add_fill_section(self, tool=False):
        """Pattern fill of a closed shape: pattern, spacing, angle, margin, outline."""
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(4)
        g.setVerticalSpacing(4)
        pattern = QComboBox()
        pattern.setIconSize(QSize(22, 22))
        pattern.addItem(_("No pattern"), "")
        for code, name in PATTERN_NAMES:
            pattern.addItem(icons.pattern_icon(code), _(name), code)
        pattern.setCurrentIndex(max(0, pattern.findData(self.spec.fill_pattern)))
        pattern.setToolTip(_("Fill the shape with engraved lines in a pattern; the outline keeps its own layer"))
        pattern.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        # tool: every choice counts, also the one already shown (it may not be on the shapes yet)
        (pattern.activated if tool else pattern.currentIndexChanged).connect(
            lambda _i: self._set("fill_pattern", pattern.currentData()))
        pattern.setProperty("spec_attr", "fill_pattern")
        g.addWidget(pattern, 0, 0, 1, 5)
        if self.spec.fill_pattern or tool:
            spacing = self._dspin("fill_spacing", 0.05, 50.0, " mm", decimals=2)
            spacing.setSingleStep(0.1)
            spacing.setToolTip(_("Size of the pattern: distance between its lines"))
            angle = self._dspin("fill_angle", -180.0, 180.0, "\u00b0")
            angle.setSingleStep(15.0)
            angle.setToolTip(_("Direction of the pattern"))
            margin = self._dspin("fill_margin", 0.0, 20.0, " mm", decimals=1)
            margin.setSingleStep(0.5)
            margin.setToolTip(_("Space kept free between the pattern and the outline"))
            outline = QToolButton()
            outline.setIcon(icons.tabler("square"))
            outline.setIconSize(QSize(18, 18))
            outline.setCheckable(True)
            outline.setChecked(self.spec.fill_outline)
            outline.setToolTip(_("Cut or engrave the outline too (off: only the pattern)"))
            outline.toggled.connect(lambda v: self._set("fill_outline", v))
            outline.setProperty("spec_attr", "fill_outline")
            g.addWidget(outline, 0, 5)
            for col, (icon, field) in enumerate((("line-height", spacing), ("rotate-2", angle), ("circle-dashed", margin))):
                g.addWidget(self._icon_label(icon, field.toolTip()), 1, 2 * col)
                g.addWidget(field, 1, 2 * col + 1)
        self._add(box, _("Fill"))

    def _with_icon(self, icon, field):
        """A field with its icon in front (both with the field's tooltip)."""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(self._icon_label(icon, field.toolTip()))
        h.addWidget(field)
        return box

    @staticmethod
    def _icon_label(icon, tip):
        """A small icon in front of a field, saying what it is (with the field's tooltip)."""
        label = QLabel()
        label.setPixmap(icons.tabler(icon).pixmap(18, 18))
        label.setToolTip(tip)
        return label

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
        w.setProperty("spec_attr", attr)          # which setting it shows (release tests check it)
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
