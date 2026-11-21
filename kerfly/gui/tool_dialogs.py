"""
The tools' windows (the user's choice 2026-11-20, modelled on Vintyl's): Fill,
Living hinge, Offset, Text and Text on a path are set up in a window with a
preview of the shape on the left (it follows every change), the kinds as
tiles with pictures and the fields on the right, and at the bottom Cancel and
the action named for what it does; a "Remove" button on the left where there
is something to remove. Nothing reaches the bed before the action is clicked.
The options bar keeps the quick things: position, size, rotation, layer, a
shape's corners and bridges.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QPlainTextEdit, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from kerfly.gui import icons, theme, widgets
from kerfly.i18n import C_, N_, _

PREVIEW_SIZE = 260                      # px: the preview of the shape (a square)
# the GUI tests answer the windows without running them: answer(dialog) -> accepted (None: the real window)
answer = None


def run(dlg):
    """Run a tool's window: True when its action (or Remove) was clicked."""
    if answer is not None:
        dlg.refresh()
        return bool(answer(dlg))
    return dlg.exec() == QDialog.Accepted


# ---- the parts -------------------------------------------------------------------------------------------
def design_lines(design):
    """[(kind, [(x, y) mm, y down])] of a design's vector parts (cut, engrave, G-code), loop by loop."""
    out = []
    for kind, part in (("cut", design.vector_cut), ("engrave", design.vector_engrave), ("gcode", design.gcode)):
        loop, pts = None, []
        for row in part.ecoords:
            if row[2] != loop:
                if len(pts) >= 2:
                    out.append((kind, pts))
                loop, pts = row[2], []
            pts.append((row[0] * 25.4, -row[1] * 25.4))
        if len(pts) >= 2:
            out.append((kind, pts))
    return out


class ShapePreview(QWidget):
    """The preview of a shape: its lines (cut red, engraved blue), a picture of it (a filled text), guide lines
    (a text's path, the shape before an offset: grey, dashed), fitted into the square."""

    def __init__(self, size=PREVIEW_SIZE, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.lines = []                 # [(kind, [(x, y)])], mm, y down
        self.guides = []                # [[(x, y)]]
        self.picture = None             # (QImage, QRectF in mm)

    def show_design(self, design, guides=()):
        self.lines = design_lines(design) if design is not None else []
        self.guides = [list(g) for g in guides]
        self.picture = None
        image = getattr(getattr(design, "raster", None), "image", None) if design is not None else None
        if image is not None:
            x0, x1, y0, y1 = design.bounds
            grey = image.convert("L")
            data = grey.tobytes()
            q = QImage(data, grey.width, grey.height, grey.width, QImage.Format_Grayscale8).copy()
            self.picture = (q, QRectF(x0 * 25.4, -y1 * 25.4, (x1 - x0) * 25.4, (y1 - y0) * 25.4))
        self.update()

    def show_lines(self, lines, guides=()):
        self.lines = list(lines)
        self.guides = [list(g) for g in guides]
        self.picture = None
        self.update()

    def _bounds(self):
        pts = [p for _k, line in self.lines for p in line] + [p for g in self.guides for p in g]
        rect = QRectF()
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if self.picture is not None:
            rect = rect.united(self.picture[1]) if not rect.isNull() else QRectF(self.picture[1])
        return rect

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.canvas("preview_paper"))
        p.setPen(QPen(theme.canvas("bed_border"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        rect = self._bounds()
        if rect.isNull() or (rect.width() <= 0 and rect.height() <= 0):
            return
        pad = 14.0
        k = min((self.width() - 2 * pad) / max(rect.width(), 1e-6), (self.height() - 2 * pad) / max(rect.height(), 1e-6))
        ox = (self.width() - rect.width() * k) / 2.0 - rect.x() * k
        oy = (self.height() - rect.height() * k) / 2.0 - rect.y() * k

        def path(points):
            pp = QPainterPath(QPointF(points[0][0] * k + ox, points[0][1] * k + oy))
            for x, y in points[1:]:
                pp.lineTo(x * k + ox, y * k + oy)
            return pp
        if self.picture is not None:
            image, r = self.picture
            p.drawImage(QRectF(r.x() * k + ox, r.y() * k + oy, r.width() * k, r.height() * k), image)
        guide = QPen(theme.canvas("outline"), 1, Qt.DashLine)
        p.setPen(guide)
        for g in self.guides:
            if len(g) >= 2:
                p.drawPath(path(g))
        colours = {"cut": theme.canvas("cut"), "engrave": theme.canvas("engrave"), "gcode": theme.canvas("gcode")}
        for kind, line in self.lines:
            p.setPen(QPen(colours.get(kind, QColor("black")), 1.2))
            p.drawPath(path(line))


class Tiles(QWidget):
    """The kinds as tiles with a picture and a name, one of them on (Vintyl's pattern picker); changed(code)."""
    changed = Signal(str)

    def __init__(self, options, current, columns=4, icon=40, parent=None):
        """options: [(code, name, QIcon)]."""
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(theme.SPACE_S)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for n, (code, name, ic) in enumerate(options):
            b = QToolButton()
            b.setText(name)
            b.setToolTip(name)
            b.setIcon(ic)
            b.setIconSize(QSize(icon, icon))
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setMinimumWidth(icon + 2 * theme.SPACE_L + 24)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)     # all as wide as each other
            b.setProperty("tile", code)
            widgets.set_role(b, "tile")
            self.group.addButton(b)
            self.buttons[code] = b
            grid.addWidget(b, n // columns, n % columns)
            b.toggled.connect(lambda on, c=code: on and self.changed.emit(c))
        for c in range(columns):
            grid.setColumnStretch(c, 1)
        self.set_current(current)

    def current(self):
        return next((c for c, b in self.buttons.items() if b.isChecked()), None)

    def set_current(self, code):
        if code in self.buttons:
            self.buttons[code].setChecked(True)


class ToolDialog(QDialog):
    """The window of a tool: the preview on the left (with a caption and a line of what is worked out), on the
    right the tiles and the fields; Cancel and the named action at the bottom, a Remove button on the left
    when given. self.render() -> (design or None, guides, status text): the preview follows every change."""

    def __init__(self, parent, title, action, remove=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.removed = False
        self.render = lambda: (None, (), "")
        body = widgets.DialogBody()
        row = QHBoxLayout()
        row.setSpacing(theme.PAD_DIALOG)
        left = QVBoxLayout()
        left.setSpacing(theme.SPACE_S)
        self.preview = ShapePreview()
        caption = widgets.hint(_("Preview of your shape"), wrap=False)
        caption.setAlignment(Qt.AlignCenter)
        self.status = widgets.hint("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedWidth(PREVIEW_SIZE)
        left.addWidget(self.preview)
        left.addWidget(caption)
        left.addWidget(self.status)
        left.addStretch(1)
        self.right = QVBoxLayout()
        self.right.setSpacing(theme.SPACE_L)
        self.section = widgets.Section()
        row.addLayout(left)
        right_box = QFrame()
        right_box.setObjectName("tool_dialog_fields")
        right_box.setLayout(self.right)
        row.addWidget(right_box, 1)
        body.layout().addLayout(row)
        self.footer = widgets.DialogFooter(action)
        self.footer.connect(self)
        self.remove_button = None
        if remove:
            self.remove_button = QPushButton(remove)
            widgets.DialogFooter.style_button(self.remove_button, "secondary")
            self.remove_button.clicked.connect(self._remove)
            self.footer.layout().insertWidget(0, self.remove_button)
        widgets.dialog_layout(self, body, self.footer)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)                  # a pause in typing, then the preview
        self._timer.timeout.connect(self.refresh)
        self.fields = {}

    def _remove(self):
        self.removed = True
        self.accept()

    def add_tiles(self, tiles):
        self.right.addWidget(tiles)
        tiles.changed.connect(lambda _c: self.changed())

    def add_field(self, attr, icon, caption, tip, field):
        """A field with its icon, caption and tooltip; attr names it (spec_attr, as on the options bar)."""
        field.setProperty("spec_attr", attr)
        if not field.toolTip():
            field.setToolTip(tip)
        self.section.add_row(icon, caption, tip, field)
        self.fields[attr] = field
        return field

    def finish(self, hint=None):
        """The fields' section and an explanation below them; the first preview."""
        self.right.addWidget(self.section)
        if hint:
            self.right.addWidget(widgets.hint(hint))
        self.right.addStretch(1)
        self.setMinimumWidth(theme.DIALOG_LARGE)
        self.refresh()

    def changed(self, *_args):
        self._timer.start()

    def refresh(self):
        try:
            design, guides, text = self.render()
        except Exception as e:                         # (a value the shape cannot take: said, not raised)
            design, guides, text = None, (), _("Cannot work it out: %s") % e
        self.preview.show_design(design, guides)
        self.status.setText(text or "")


def number(value, lo, hi, suffix, decimals=1, step=None):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSuffix(suffix)
    w.setValue(float(value))
    w.setKeyboardTracking(True)
    if step:
        w.setSingleStep(step)
    return w


def _watch(dialog, *fields):
    for f in fields:
        for name in ("valueChanged", "toggled", "textChanged", "family_chosen"):
            sig = getattr(f, name, None)
            if sig is not None:
                sig.connect(dialog.changed)
                break


def _design_of(spec):
    from kerfly.core.shapes import build_design
    from kerfly.gui.text_shapes import update_text_spec
    if spec.kind == "text":
        update_text_spec(spec)
    return build_design(spec)


# ---- the tools' windows -------------------------------------------------------------------------------------
def fill_dialog(parent, spec, show=True, had=None):
    """The Fill window for a shape (spec: its ShapeSpec, the pattern to start with in it; had: the shape has a
    fill now, for the Remove button). Returns the new spec, "remove" (Remove the fill) or None (Cancel).
    show=False: the window, not run (tests)."""
    from kerfly.gui.tool_options import PATTERN_NAMES
    work = spec.copy()
    had = bool(spec.fill_pattern) if had is None else had
    if not work.fill_pattern:
        work.fill_pattern = "lines"
    dlg = ToolDialog(parent, _("Fill"), _("Fill it"), remove=_("Remove the fill") if had else None)
    tiles = Tiles([(c, _(n), icons.pattern_icon(c)) for c, n in PATTERN_NAMES], work.fill_pattern, columns=5)
    dlg.add_tiles(tiles)
    spacing = dlg.add_field("fill_spacing", "line-height", _("Spacing"), _("Size of the pattern: distance between "
                            "its lines"), number(work.fill_spacing, 0.05, 50.0, " mm", 2, 0.1))
    angle = dlg.add_field("fill_angle", "rotate-2", _("Angle"), _("Direction of the pattern"),
                          number(work.fill_angle, -180.0, 180.0, "°", 1, 15.0))
    margin = dlg.add_field("fill_margin", "circle-dashed", _("Margin"), _("Space kept free between the pattern "
                           "and the outline"), number(work.fill_margin, 0.0, 20.0, " mm", 1, 0.5))
    outline = QCheckBox(_("Cut or engrave the outline too"))
    outline.setChecked(work.fill_outline)
    dlg.add_field("fill_outline", "square", _("Outline"), _("Off: only the pattern"), outline)
    dlg.tiles = tiles

    def values():
        s = spec.copy()
        s.fill_pattern = tiles.current() or "lines"
        s.fill_spacing, s.fill_angle, s.fill_margin = spacing.value(), angle.value(), margin.value()
        s.fill_outline = outline.isChecked()
        if s.operation == "hatch":
            s.operation = "engrave"
        return s
    dlg.values = values
    dlg.render = lambda: (_design_of(values()), (), "")
    _watch(dlg, spacing, angle, margin, outline)
    dlg.finish(_("The pattern is engraved; the outline keeps its own layer (cut or outline)."))
    if not show:
        return dlg
    if not run(dlg):
        return None
    return "remove" if dlg.removed else values()


def hinge_dialog(parent, spec, show=True, had=None):
    """The Living hinge window for a shape (had: it has a hinge now). Returns the new spec, "remove" or None
    (Cancel)."""
    from kerfly.gui.tool_options import HINGE_NAMES
    work = spec.copy()
    had = bool(spec.hinge_pattern) if had is None else had
    if not work.hinge_pattern:
        work.hinge_pattern = "straight"
    dlg = ToolDialog(parent, _("Living hinge"), _("Cut the hinge"), remove=_("Remove the hinge") if had else None)
    tiles = Tiles([(c, _(n), icons.hinge_pattern_icon(c)) for c, n in HINGE_NAMES], work.hinge_pattern, columns=3)
    dlg.add_tiles(tiles)
    fields = (("hinge_cut", 1.0, 500.0, " mm", 0.5, "ruler-measure", C_("hinge", "Cut"), N_("Length of one cut")),
              ("hinge_gap", 0.2, 50.0, " mm", 0.5, "link", C_("hinge", "Bridge"),
               N_("Bridge: uncut material between two cuts in a row")),
              ("hinge_spacing", 0.2, 50.0, " mm", 0.5, "line-height", _("Row gap"),
               N_("Distance between the rows of cuts (smaller: bends more)")),
              ("hinge_angle", -180.0, 180.0, "°", 90.0, "rotate-2", _("Angle"),
               N_("Direction of the cuts (90°: up and down; the sheet bends across them)")),
              ("hinge_margin", 0.0, 100.0, " mm", 0.5, "circle-dashed", _("Margin"),
               N_("Solid material at the ends of the hinge, across the rows (the cuts themselves reach the "
                  "outline, or the sheet would not bend)")),
              ("hinge_band", 0.0, 2000.0, " mm", 0.5, "arrows-horizontal", _("Band width"),
               N_("Width of the hinge band, across the cuts (0: the whole shape)")),
              ("hinge_band_offset", -2000.0, 2000.0, " mm", 0.5, "focus-centered", _("Band offset"),
               N_("Where the band is: its middle from the middle of the shape (minus: left / up, plus: right / "
                  "down)")))
    spins = {}
    for attr, lo, hi, unit, step, ic, caption, tip in fields:
        spins[attr] = dlg.add_field(attr, ic, caption, _(tip), number(getattr(work, attr), lo, hi, unit, 1, step))
    dlg.tiles = tiles

    def values():
        s = spec.copy()
        s.hinge_pattern = tiles.current() or "straight"
        for attr, w in spins.items():
            setattr(s, attr, w.value())
        return s
    dlg.values = values

    def render():
        s = values()
        d = _design_of(s)
        cuts = sum(1 for kind, _l in design_lines(d) if kind == "cut") - 1
        return d, (), ngettext_cuts(max(0, cuts))
    dlg.render = render
    _watch(dlg, *spins.values())
    dlg.finish(_("The cuts reach the outline at the ends of every second row; the sheet bends across them. Try "
                 "a small piece first: how far it bends depends on the material."))
    if not show:
        return dlg
    if not run(dlg):
        return None
    return "remove" if dlg.removed else values()


def ngettext_cuts(n):
    from kerfly.i18n import ngettext
    return ngettext("%d cut", "%d cuts", n) % n


def offset_dialog(parent, polys, values, show=True):
    """The Offset window: polys are the chosen shapes' closed outlines (scene mm, y down); values the tool's
    settings (offset_distance, offset_join, offset_keep). Returns the new values or None (Cancel)."""
    from kerfly.core import offset
    dlg = ToolDialog(parent, _("Offset"), _("Offset"))
    tiles = Tiles([("round", _("Round corners"), icons.tabler("border-radius")),
                   ("miter", _("Sharp corners"), icons.tabler("border-corners"))],
                  values.get("offset_join", "round"), columns=2, icon=32)
    dlg.add_tiles(tiles)
    distance = dlg.add_field("offset_distance", "arrows-diagonal", _("Distance"),
                             _("How far the new outline lies from the shape (minus: inside it)"),
                             number(values.get("offset_distance", 2.0), -500.0, 500.0, " mm", 2, 0.5))
    keep = QCheckBox(_("Keep the shape (off: replace it)"))
    keep.setChecked(bool(values.get("offset_keep", True)))
    dlg.add_field("offset_keep", "copy", _("Original"), _("Keep the shape and add the new outline, or replace "
                                                          "the shape with it"), keep)
    dlg.tiles = tiles

    def now():
        return {"offset_distance": distance.value(), "offset_join": tiles.current() or "round",
                "offset_keep": keep.isChecked()}
    dlg.values = now

    def render():
        v = now()
        guides = [[(x, y) for x, y in poly] for shape in polys for poly in shape]
        lines = []
        if abs(v["offset_distance"]) > 1e-9:
            for shape in polys:
                for ring in offset.offset_polygons(shape, v["offset_distance"], v["offset_join"]):
                    lines.append(("cut", [(x, y) for x, y in ring]))
        dlg.preview.show_lines(lines, guides)
        return None, guides, "" if lines else _("Set a distance other than 0.")

    def refresh():
        try:
            _d, _g, text = render()
        except Exception as e:
            text = _("Cannot work it out: %s") % e
        dlg.status.setText(text)
    dlg.refresh = refresh
    _watch(dlg, distance, keep)
    dlg.finish(_("The closed outlines are joined first, so a hole moves the other way."))
    if not show:
        return dlg
    if not run(dlg):
        return None
    return now()


def text_dialog(parent, spec, title, action, show=True, path_fields=False):
    """The Text window: its content, font, size, bold, italic, letter spacing; on a path also where it starts,
    its distance from the line and the side ("Straight text" takes it off the path). Returns the new spec,
    "straight" or None (Cancel)."""
    from kerfly.gui.font_box import FontBox
    work = spec.copy()
    dlg = ToolDialog(parent, title, action,
                     remove=_("Straight text") if path_fields and spec.text_path else None)
    text = QPlainTextEdit(work.text)
    text.setPlaceholderText(_("Text"))
    text.setFixedHeight(4 * theme.HEIGHT_FIELD)
    text.setTabChangesFocus(True)
    dlg.right.addWidget(text)
    text.setProperty("spec_attr", "text")
    text.setToolTip(_("Text; press Enter for a new line"))
    dlg.fields["text"] = text
    font = FontBox()
    font.set_family(work.font_family)
    font.setToolTip(_("Font. At the top of the list: single-line fonts, built into Kerfly, for fast engraving "
                      "(the laser runs once along each letter, nothing to fill)"))
    dlg.add_field("font_family", "text-size", _("Font"), font.toolTip(), font)
    size = dlg.add_field("font_size", "text-resize", _("Size"), _("Height of the letters"),
                         number(work.font_size, 0.5, 500.0, " mm", 1, 0.5))
    style = QWidget()
    srow = QHBoxLayout(style)
    srow.setContentsMargins(0, 0, 0, 0)
    bold = QCheckBox(_("Bold"))
    bold.setChecked(work.bold)
    italic = QCheckBox(_("Italic"))
    italic.setChecked(work.italic)
    bold.setProperty("spec_attr", "bold")
    italic.setProperty("spec_attr", "italic")
    srow.addWidget(bold)
    srow.addWidget(italic)
    srow.addStretch(1)
    dlg.section.add_row("bold", _("Style"), _("Bold and italic letters"), style)
    dlg.fields["bold"], dlg.fields["italic"] = bold, italic
    spacing = dlg.add_field("text_spacing", "letter-spacing", _("Letter spacing"),
                            _("Space added between the letters (0: as the font sets it)"),
                            number(work.text_spacing, -50.0, 200.0, " mm", 2, 0.1))
    path_widgets = []
    if path_fields:
        start = dlg.add_field("text_path_offset", "route", C_("text path", "Start"), _("Position along the path: where the text "
                              "starts"), number(work.text_path_offset, -5000.0, 5000.0, " mm", 1, 1.0))
        distance = dlg.add_field("text_path_distance", "line-height", _("From line"), _("Distance from the line: "
                                 "space between the line and the foot of the letters (minus: the letters cross "
                                 "the line)"), number(work.text_path_distance, -500.0, 500.0, " mm", 1, 0.5))
        flip = QCheckBox(_("Other side (the text runs the other way)"))
        flip.setChecked(work.text_path_flip)
        dlg.add_field("text_path_flip", "flip-vertical", _("Side"), _("The text on the other side of the line"),
                      flip)
        path_widgets = [start, distance, flip]

    def values():
        s = spec.copy()
        s.text = text.toPlainText()
        s.font_family = font.family() if hasattr(font, "family") else font.currentFont().family()
        s.font_size, s.text_spacing = size.value(), spacing.value()
        s.bold, s.italic = bold.isChecked(), italic.isChecked()
        if path_fields:
            s.text_path_offset, s.text_path_distance = path_widgets[0].value(), path_widgets[1].value()
            s.text_path_flip = path_widgets[2].isChecked()
        return s
    dlg.values = values

    def render():
        s = values()
        if not s.text.strip():
            return None, (), _("Type the text.")
        d = _design_of(s)
        guides = []
        if s.text_path:
            # the path is in the outlines' frame (y down, top at 0: update_text_spec); the design's lines
            # come with their top at -(its top) (design_lines): the path moved the same way, so the text
            # sits on it as on the bed (it was drawn a text's height off: the user's test 2026-11-21)
            top = d.bounds[3] * 25.4
            guides = [[(x, y - top) for x, y in s.text_path]]
        return d, guides, ""
    dlg.render = render
    _watch(dlg, text, font, size, bold, italic, spacing, *path_widgets)
    dlg.finish()
    text.setFocus()
    text.selectAll()
    if not show:
        return dlg
    if not run(dlg):
        return None
    if dlg.removed:
        return "straight"
    return values()
