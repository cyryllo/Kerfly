"""
Options bar above the bed view: settings of the selected shape, or of the
drawing tool in use (like LightBurn's tool options bar). This is its second
row (docs/ui-mockups/OptionBars): the name of what is edited in bold, then
groups of fields, each field with its icon, a short caption and a tooltip,
the groups apart by thin lines. The first row (the selection's position,
size, rotation and layer) is the window's.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox,
                               QToolButton, QWidget)

from kerfly.gui import icons, theme, widgets
from kerfly.gui.sizing import chars_width
from kerfly.i18n import C_, N_, _

OPERATION_NAMES = [("cut", N_("Cut")), ("engrave", N_("Engrave outline")), ("fill", N_("Fill (raster)"))]
KIND_NAMES = {"rectangle": N_("Rectangle"), "ellipse": N_("Ellipse"), "polygon": N_("Polygon"),
              "line": N_("Line"), "polyline": N_("Polyline"), "path": N_("Path"), "pen": N_("Path"), "freehand": N_("Freehand"),
              "text": N_("Text")}
# fill patterns (kerfly.core.patterns.PATTERNS), names for the GUI
PATTERN_NAMES = [("lines", N_("Lines")), ("cross", N_("Cross-hatch")), ("waves", N_("Waves")),
                 ("zigzag", N_("Zigzag")), ("circles", N_("Circles")), ("honeycomb", N_("Honeycomb")),
                 ("diamonds", N_("Diamonds")), ("bricks", N_("Bricks")), ("concentric", N_("Concentric")),
                 ("triangles", N_("Triangles")), ("herringbone", N_("Herringbone")), ("scales", N_("Fish scales")),
                 ("squarewave", N_("Square waves")), ("spiral", N_("Spiral")), ("radial", N_("Sunburst")),
                 ("dots", N_("Dots")), ("crosses", N_("Crosses")), ("truchet", N_("Truchet")),
                 ("hilbert", N_("Hilbert curve"))]
# living hinges (kerfly.core.patterns.HINGES), names for the GUI
HINGE_NAMES = [("straight", N_("Straight cuts")), ("wave", N_("Wavy cuts")), ("zigzag", N_("Zigzag cuts"))]
NEW_KIND_TITLES = {"rectangle": N_("New rectangle"), "ellipse": N_("New ellipse"),
                   "polygon": N_("New polygon"), "line": N_("New line"),
                   "polyline": N_("New polyline"), "pen": N_("New path"),
                   "freehand": N_("New freehand line"), "text": N_("New text"),
                   "textpath": N_("New text on a path")}


def ribbon_separator():
    """A thin vertical line between the ribbon's groups."""
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setObjectName("ribbon_separator")
    return line


def option_field(icon, caption, field, tip=None):
    """A field of the options bar: its icon, its short caption and the field, all with the tooltip
    (icon None: the caption alone, e.g. X and Y)."""
    tip = tip or field.toolTip()
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(theme.SPACE_S)
    if icon is not None:
        row.addWidget(widgets.icon_pixmap_label(icon, tip))
    if caption:
        label = widgets.label(caption, "hint", wrap=False)
        label.setToolTip(tip)
        row.addWidget(label)
        row.addSpacing(theme.SPACE_S)
    row.addWidget(field)
    if not field.toolTip():
        field.setToolTip(tip)
    return box


def option_title(text):
    """The bold name at the start of a row of the options bar (what is edited)."""
    label = widgets.section_title(text)
    label.setMinimumWidth(theme.OPTION_TITLE)
    label.setMaximumWidth(2 * theme.OPTION_TITLE)
    label.setToolTip(text)
    return label


def text_button(icon, text, tip, checkable=False):
    """A small button with its icon and a short text (Keep the original, Other side, ...)."""
    b = QToolButton()
    b.setIcon(icons.tabler(icon) if isinstance(icon, str) else icon)
    b.setIconSize(QSize(theme.ICON, theme.ICON))
    b.setText(text)
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.setFixedHeight(theme.HEIGHT_FIELD)
    b.setAutoRaise(not checkable)
    return b


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
    crop_changed = Signal(dict)         # the Cut out of picture tool's settings
    offset_apply = Signal()             # the Offset tool's "Offset selected" button
    rebuilt = Signal()                  # its fields changed (the window fits the bar's width)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tool_options")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(theme.SPACE_M)
        self.spec = None
        self._groups = 0
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.setInterval(400)       # rebuild text outlines after typing pauses
        self._text_timer.timeout.connect(self._emit)
        self.show_hint()

    # ---- building -------------------------------------------------------
    def _clear(self, title=None):
        """Empty the row; title: the bold name it starts with."""
        self._text_timer.stop()
        self._node_buttons = []                  # their widgets are deleted below
        while self.row.count():
            item = self.row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()                 # gone now, not only when Qt deletes it later
                w.setParent(None)
                w.deleteLater()
        self._groups = 0
        if title:
            self.row.addWidget(option_title(title))

    def _add(self, *items):
        """A group of fields (widgets), after a thin line."""
        if self.row.count():
            self.row.addWidget(widgets.separator())
        for item in items:
            self.row.addWidget(item)
            item.show()          # at once: Qt shows a widget added to a shown bar only after the event loop
        self._groups += 1

    def _end(self):
        self.row.addStretch(1)                       # keep the groups together on the left
        self.rebuilt.emit()

    def show_hint(self):
        """Nothing to edit: an empty row (the bar keeps its height)."""
        self.spec = None
        self._clear()
        self._end()

    def add_node_actions(self):
        """Buttons of the node tool, in groups, with icons and their key. Those that need a
        selected node are greyed out until a node is clicked."""
        self._node_buttons = []
        last = self.row.itemAt(self.row.count() - 1) if self.row.count() else None
        if last is not None and last.spacerItem() is not None:
            self.row.takeAt(self.row.count() - 1)     # the stretch goes after the node groups
        if not self.row.count():
            self.row.addWidget(option_title(_("Nodes")))
        for section, actions in NODE_SECTIONS:
            group = []
            for code, label, icon, key, tip, needs_node in actions:
                b = text_button(icon, "%s (%s)" % (_(label), key), "%s: %s (%s)" % (_(section), _(tip), key))
                b.clicked.connect(lambda _c=False, c=code: self.node_action.emit(c))
                group.append(b)
                self._node_buttons.append((b, needs_node))
            self._add(*group)
        self._end()
        self.set_node_selection(0)

    def set_node_selection(self, count):
        """Enable the node buttons that need a selected node, and say what to do."""
        for b, needs_node in getattr(self, "_node_buttons", []):
            try:
                b.setEnabled(count > 0 or not needs_node)
            except RuntimeError:
                pass                             # the bar was rebuilt meanwhile

    def show_crop_tool(self, values):
        """Options of the Cut out of picture tool: the shape of the piece that stays."""
        self.spec = None
        self._clear(_("Cut out of a picture"))
        self.crop_values = dict(values)
        shape = QComboBox()
        for code, icon, name in (("rect", "square", N_("Rectangle")), ("ellipse", "circle", N_("Ellipse"))):
            shape.addItem(icons.tabler(icon), _(name), code)
        shape.setCurrentIndex(max(0, shape.findData(values.get("crop_shape", "rect"))))
        shape.setToolTip(_("Shape of the piece that stays: drag it over a picture; the rest of the picture goes"))
        shape.currentIndexChanged.connect(lambda _i, c=shape: self._set_crop("crop_shape", c.currentData()))
        self.crop_shape_box = shape
        self._add(option_field("picture-cut", _("Shape"), shape))
        self._end()

    def _set_crop(self, key, value):
        self.crop_values[key] = value
        self.crop_changed.emit(dict(self.crop_values))

    def show_picture(self, actions):
        """A selected picture: its commands (Trace)."""
        self.spec = None
        self._clear(_("Picture"))
        for act in actions:
            b = QToolButton()
            b.setDefaultAction(act)
            b.setIconSize(QSize(theme.ICON, theme.ICON))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setFixedHeight(theme.HEIGHT_FIELD)
            b.setAutoRaise(True)
            self._add(b)
        self._end()

    def show_spec(self, spec, title):
        """Show the options of spec (a ShapeSpec); title names what is edited."""
        self.spec = spec.copy()
        self._clear(title)
        # what the laser does with the shape is chosen with its layer (the first row, Layer)
        kind = self.spec.kind
        if kind == "rectangle":
            radius = self._dspin("corner_radius", 0.0, 1000.0, " mm")
            radius.setToolTip(_("Corner radius: 0 for sharp corners"))
            self._add(option_field("border-radius", _("Corner radius"), radius))
        elif kind == "polygon":
            sides = QSpinBox()
            sides.setRange(3, 64)
            sides.setValue(self.spec.sides)
            sides.setKeyboardTracking(False)
            sides.setToolTip(_("Number of sides of the regular polygon"))
            sides.valueChanged.connect(lambda v: self._set("sides", v))
            sides.setProperty("spec_attr", "sides")
            self._add(option_field("hexagon", _("Sides"), sides))
        elif kind == "text":
            self._add_text_fields()

        if self.spec.operation == "cut" and self.spec.closed:
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
            self._add(option_field("hash", _("Bridges"), count),
                      option_field("arrows-horizontal", _("Bridge width"), width))

        if self.spec.operation in ("cut", "engrave") and self.spec.closed:
            self._add_fill_section()
            if self.spec.hinge_pattern:                  # added with the Living hinge tool
                self._add_hinge_section()
        self._end()

    def _add_text_fields(self):
        """A text: its content, font, size, bold and italic, letter spacing; on a path its place on it."""
        text = QPlainTextEdit(self.spec.text)
        text.setPlaceholderText(_("Text"))
        text.setToolTip(_("Text; press Enter for a new line"))
        text.setFixedSize(chars_width(text, 16), theme.HEIGHT_FIELD)
        text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        text.setTabChangesFocus(True)
        text.textChanged.connect(lambda: self._text_edited(text.toPlainText()))
        text.setProperty("spec_attr", "text")
        from kerfly.gui.font_box import FontBox
        font = FontBox()
        font.set_family(self.spec.font_family)
        font.setFixedWidth(chars_width(font, 16) + 28)
        font.setToolTip(_("Font. At the top of the list: single-line fonts, built into Kerfly, for fast "
                          "engraving (the laser runs once along each letter, nothing to fill)"))
        font.family_chosen.connect(lambda fam: self._set("font_family", fam)
                                   if self.spec is not None and fam != self.spec.font_family else None)
        font.setProperty("spec_attr", "font_family")
        size = self._dspin("font_size", 0.5, 500.0, " mm")
        style = []
        for attr, icon, tip in (("bold", "bold", N_("Bold")), ("italic", "italic", N_("Italic"))):
            b = widgets.icon_button(icon, _(tip), checkable=True)
            b.setChecked(getattr(self.spec, attr))
            b.toggled.connect(lambda on, a=attr: self._set(a, on))
            b.setProperty("spec_attr", attr)
            style.append(b)
        spacing = self._dspin("text_spacing", -50.0, 200.0, " mm", decimals=2)
        spacing.setSingleStep(0.1)
        spacing.setToolTip(_("Letter spacing: space added between the letters (0: as the font sets it)"))
        self._add(option_field("typography", _("Content"), text),
                  option_field("text-size", _("Font"), font), option_field(None, _("Size"), size), *style,
                  option_field("letter-spacing", _("Letter spacing"), spacing))
        if self.spec.text_path:
            offset = self._dspin("text_path_offset", -5000.0, 5000.0, " mm")
            offset.setSingleStep(1.0)
            offset.setToolTip(_("Position along the path: where the text starts (you can also drag the text "
                                "with the mouse)"))
            distance = self._dspin("text_path_distance", -500.0, 500.0, " mm")
            distance.setSingleStep(0.5)
            distance.setToolTip(_("Distance from the line: space between the line and the foot of the letters "
                                  "(minus: the letters cross the line)"))
            flip = text_button("flip-vertical", _("Other side"),
                               _("Other side: the text runs the other way, on the other side of the line"),
                               checkable=True)
            flip.setChecked(self.spec.text_path_flip)
            flip.toggled.connect(lambda v: self._set("text_path_flip", v))
            flip.setProperty("spec_attr", "text_path_flip")
            straight = text_button("slash", _("Straight text"),
                                   _("Take the text off the path: back to a straight line of text"))
            straight.clicked.connect(lambda: self._set("text_path", []))
            self._add(option_field("route", _("Start"), offset), option_field("line-height", _("From line"), distance),
                      flip, straight)

    def show_fill_tool(self, spec):
        """Options of the Fill tool: the pattern given to the shapes it is clicked on."""
        self.spec = spec.copy()
        self._clear(_("Fill"))
        self._add_fill_section(tool=True)       # what to do is said in the status bar
        self._end()

    def show_offset_tool(self, values):
        """Options of the Offset tool: how far the new outline lies from the shape,
        its corners, keep the shape or replace it; a button for the selected shapes."""
        self.spec = None
        self._clear(_("Offset"))
        self.offset_values = dict(values)
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
        join = QComboBox()
        join.addItem(icons.tabler("border-radius"), _("Round"), "round")
        join.addItem(icons.tabler("square"), _("Sharp"), "miter")
        join.setCurrentIndex(max(0, join.findData(values["offset_join"])))
        join.setToolTip(_("Corners of the new outline: rounded, or sharp like the shape's"))
        join.setProperty("spec_attr", "offset_join")
        join.currentIndexChanged.connect(lambda _i: self._set_offset("offset_join", join.currentData()))
        keep = text_button("copy", _("Keep the original"),
                           _("On: the new outline is added next to the shape; off: it replaces the shape"),
                           checkable=True)
        keep.setChecked(bool(values["offset_keep"]))
        keep.setProperty("spec_attr", "offset_keep")
        keep.toggled.connect(lambda on: self._set_offset("offset_keep", on))
        apply = text_button("box-padding", _("Offset selected"),
                            _("Draw the new outline around the shapes selected now (or click a shape on the bed)"))
        apply.clicked.connect(self.offset_apply.emit)
        self.offset_apply_button = apply
        self._add(option_field("arrows-horizontal", _("Distance"), distance),
                  option_field("border-radius", _("Corners"), join), keep)
        self._add(apply)
        self._end()

    def _set_offset(self, key, value):
        self.offset_values[key] = value
        self.offset_changed.emit(dict(self.offset_values))

    def show_hinge_tool(self, spec):
        """Options of the Living hinge tool: the cuts given to the shapes it is clicked on."""
        self.spec = spec.copy()
        self._clear(_("Living hinge"))
        self._add_hinge_section(tool=True)      # what to do is said in the status bar
        self._end()

    def _add_hinge_section(self, tool=False):
        """Living hinge of a closed shape: pattern, cut length, bridge, row spacing,
        direction, solid border, the band."""
        pattern = QComboBox()
        pattern.setIconSize(QSize(theme.ICON, theme.ICON))
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
        items = [option_field(icons.hinge_icon(), _("Living hinge"), pattern)]
        if self.spec.hinge_pattern or tool:
            # (field, from, to, unit, icon, short caption, tooltip)
            fields = (("hinge_cut", 1.0, 500.0, " mm", "ruler-measure", C_("hinge", "Cut"),
                       N_("Length of one cut")),
                      ("hinge_gap", 0.2, 50.0, " mm", "link", C_("hinge", "Bridge"),
                       N_("Bridge: uncut material between two cuts in a row")),
                      ("hinge_spacing", 0.2, 50.0, " mm", "line-height", _("Row gap"),
                       N_("Distance between the rows of cuts (smaller: bends more)")),
                      ("hinge_angle", -180.0, 180.0, "\u00b0", "rotate-2", _("Angle"),
                       N_("Direction of the cuts (90\u00b0: up and down; the sheet bends across them)")),
                      ("hinge_margin", 0.0, 100.0, " mm", "circle-dashed", _("Margin"),
                       N_("Solid border: no cuts this close to the outline")),
                      ("hinge_band", 0.0, 2000.0, " mm", "arrows-horizontal", _("Band width"),
                       N_("Width of the hinge band, across the cuts (0: the whole shape)")),
                      ("hinge_band_offset", -2000.0, 2000.0, " mm", "focus-centered", _("Band offset"),
                       N_("Where the band is: its middle from the middle of the shape (minus: left / up, "
                          "plus: right / down)")))
            for attr, lo, hi, unit, icon, caption, tip in fields:
                w = self._dspin(attr, lo, hi, unit)
                w.setSingleStep(90.0 if attr == "hinge_angle" else 0.5)
                w.setToolTip(_(tip))
                items.append(option_field(icon, caption, w))
        self._add(*items)

    def _add_fill_section(self, tool=False):
        """Pattern fill of a closed shape: pattern, spacing, angle, margin, outline."""
        pattern = QComboBox()
        pattern.setIconSize(QSize(theme.ICON, theme.ICON))
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
        items = [option_field("bucket-droplet", _("Fill"), pattern)]
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
            outline = text_button("square", _("Outline"), _("Cut or engrave the outline too (off: only the pattern)"),
                                  checkable=True)
            outline.setChecked(self.spec.fill_outline)
            outline.toggled.connect(lambda v: self._set("fill_outline", v))
            outline.setProperty("spec_attr", "fill_outline")
            items += [option_field("line-height", _("Spacing"), spacing), option_field("rotate-2", _("Angle"), angle),
                      option_field("circle-dashed", _("Margin"), margin), outline]
        self._add(*items)

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
