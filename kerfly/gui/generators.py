"""
Generators in the window: the list shown in the Generators group of the
toolbar and menu, and the dialog that asks for a generator's numbers, shows
a preview and remembers the last numbers used.

Each generator: (key, title, icon, tooltip, fields, make). fields:
(name, label, kind, default, options, tooltip) with kind "float" (min, max,
decimals, unit), "int" (min, max), "choice" ([(value, label)]), "bool" or
"text". make(values, window) returns a kerfly.core.generators.Generated.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFontComboBox, QFormLayout, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from kerfly.core import generators as gen
from kerfly.core.layers import DEFAULT_COLORS
from kerfly.core.shapes import outlines
from kerfly.i18n import N_, _

OPERATIONS = [("engrave", N_("Engrave outline")), ("cut", N_("Cut")), ("fill", N_("Fill (raster)"))]


def _speed_unit(window):
    return "mm/s" if window.values.get("units", "mm") == "mm" else "in/min"


def _material_test(v, window):
    unit = _speed_unit(window)                  # layer speeds are in the user's units, as typed
    by = v["rows_by"]
    legend = (_("Speed (%s) / power (%%)") % unit) if by == "power" else (_("Speed (%s) / passes") % unit)
    return gen.material_test(v["operation"], v["speed_min"], v["speed_max"], v["columns"], by,
                             v["power_min"], v["power_max"], v["passes_min"], v["passes_max"], v["rows"],
                             v["size"], v["gap"], v["labels"], unit, legend if v["labels"] else "")


GENERATORS = [
    ("material_test", N_("Material test"), "table",
     N_("Material test: a grid of fields, each with its own speed and power (or passes), to find the right "
        "settings for a material"),
     [("operation", N_("Operation"), "choice", "engrave", OPERATIONS, N_("What the laser does with the fields")),
      ("speed_min", N_("Speed from"), "float", 10.0, (0.1, 10000, 1, "speed"), N_("Speed of the first column")),
      ("speed_max", N_("Speed to"), "float", 50.0, (0.1, 10000, 1, "speed"), N_("Speed of the last column")),
      ("columns", N_("Columns (speeds)"), "int", 5, (1, 12), N_("How many different speeds")),
      ("rows_by", N_("Rows change"), "choice", lambda w: "power" if w.power_per_stage() else "passes",
       [("power", N_("Power (M3 boards)")), ("passes", N_("Passes"))],
       N_("What changes from row to row: the power (only M3 boards set it) or the number of passes")),
      ("power_min", N_("Power from (%)"), "float", 20.0, (0, 100, 0, None), N_("Power of the first row")),
      ("power_max", N_("Power to (%)"), "float", 60.0, (0, 100, 0, None), N_("Power of the last row")),
      ("passes_min", N_("Passes from"), "int", 1, (1, 20), N_("Passes of the first row")),
      ("passes_max", N_("Passes to"), "int", 3, (1, 20), N_("Passes of the last row")),
      ("rows", N_("Rows"), "int", 3, (1, 12), N_("How many different powers or passes")),
      ("size", N_("Field size"), "float", 10.0, (3, 50, 1, "mm"), N_("Width and height of one field")),
      ("gap", N_("Gap"), "float", 3.0, (0.5, 20, 1, "mm"), N_("Space between the fields")),
      ("labels", N_("Engrave the values"), "bool", True, None,
       N_("Engrave the speeds above the columns and the powers or passes beside the rows"))],
     _material_test),
]


def _finger_box(v, window):
    names = {"bottom": _("Bottom"), "front": _("Front"), "back": _("Back"), "left": _("Left side"),
             "right": _("Right side"), "lid": _("Lid")}
    return gen.finger_box(v["width"], v["depth"], v["height"], v["thickness"], v["finger"], v["kerf"], v["lid"],
                          v["inside"], names=names)


def _kerf_test(v, window):
    note = _("kerf = (%s mm - measured) / %d") % (("%.1f" % v["length"]).rstrip("0").rstrip("."), v["pieces"])
    return gen.kerf_test(v["length"], v["pieces"], 10.0, v["thickness"], v["fit_from"], v["fit_to"], v["fits"],
                         10.0, v["labels"], note if v["labels"] else "")


def _gear(v, window):
    return gen.gear(v["teeth"], v["module"], v["pressure_angle"], v["bore"])


def _puzzle(v, window):
    return gen.puzzle(v["width"], v["height"], v["columns"], v["rows"], v["tab"] / 100.0, v["seed"], v["outline"])


def _ruler(v, window):
    return gen.ruler(v["length"], v["width"], v["outline"], v["numbers"], v["unit"])


def _test_card(v, window):
    return gen.test_card()


def _qr(v, window):
    return gen.qr_code(v["text"], v["size"], v["error"], v["border"])


GENERATORS += [
    ("finger_box", N_("Finger-joint box"), "box",
     N_("Finger-joint box: the bottom, four walls and a lid that fit together with fingers"),
     [("width", N_("Width"), "float", 100.0, (20, 1000, 1, "mm"), N_("Width of the box (left to right)")),
      ("depth", N_("Depth"), "float", 80.0, (20, 1000, 1, "mm"), N_("Depth of the box (front to back)")),
      ("height", N_("Height"), "float", 50.0, (10, 1000, 1, "mm"), N_("Height of the box")),
      ("inside", N_("Inside sizes"), "bool", False, None,
       N_("The sizes are the inside of the box (off: the outside)")),
      ("thickness", N_("Material thickness"), "float", 3.0, (0.5, 20, 2, "mm"), N_("Thickness of the sheet")),
      ("finger", N_("Finger width"), "float", 10.0, (2, 100, 1, "mm"),
       N_("About how wide one finger is (each edge gets an odd number of equal fingers)")),
      ("kerf", N_("Kerf"), "float", 0.15, (0, 1, 2, "mm"),
       N_("Width of the laser's cut: the parts grow by half of it so the fingers fit tightly "
          "(measure it with the kerf test)")),
      ("lid", N_("With a lid"), "bool", True, None, N_("Six parts with a lid (off: an open box of five parts)"))],
     _finger_box),
    ("kerf_test", N_("Kerf test"), "ruler-2",
     N_("Kerf test: a comb to measure how wide the laser cuts, and slots to find the tightest fit for the "
        "material"),
     [("length", N_("Comb length"), "float", 50.0, (20, 300, 1, "mm"), N_("Length of the comb before cutting")),
      ("pieces", N_("Comb pieces"), "int", 10, (2, 30), N_("Into how many pieces the comb is cut")),
      ("thickness", N_("Material thickness"), "float", 3.0, (0.5, 20, 2, "mm"),
       N_("Thickness of the sheet: the slots are this wide plus the clearance")),
      ("fit_from", N_("Clearance from"), "float", -0.2, (-2, 2, 2, "mm"), N_("Clearance of the first slot")),
      ("fit_to", N_("Clearance to"), "float", 0.1, (-2, 2, 2, "mm"), N_("Clearance of the last slot")),
      ("fits", N_("Slots"), "int", 7, (1, 12), N_("How many slots")),
      ("labels", N_("Engrave the values"), "bool", True, None, N_("Engrave the clearances under the slots"))],
     _kerf_test),
    ("gear", N_("Gear"), "settings-2",
     N_("Gear: a spur gear with involute teeth and a hole for the axle"),
     [("teeth", N_("Teeth"), "int", 20, (6, 200), N_("Number of teeth")),
      ("module", N_("Module"), "float", 2.0, (0.3, 20, 2, "mm"),
       N_("Size of the teeth: the pitch diameter is the module times the number of teeth; gears that mesh "
          "need the same module")),
      ("pressure_angle", N_("Pressure angle"), "float", 20.0, (14.5, 30, 1, "°"),
       N_("Shape of the teeth (20° is usual; meshing gears need the same angle)")),
      ("bore", N_("Axle hole"), "float", 5.0, (0, 200, 1, "mm"), N_("Diameter of the hole in the middle (0: none)"))],
     _gear),
    ("puzzle", N_("Puzzle"), "puzzle",
     N_("Puzzle: a jigsaw puzzle cut, for example over an engraved picture"),
     [("width", N_("Width"), "float", 150.0, (20, 1000, 1, "mm"), N_("Width of the puzzle")),
      ("height", N_("Height"), "float", 100.0, (20, 1000, 1, "mm"), N_("Height of the puzzle")),
      ("columns", N_("Columns"), "int", 5, (2, 40), N_("Pieces from left to right")),
      ("rows", N_("Rows"), "int", 4, (2, 40), N_("Pieces from top to bottom")),
      ("tab", N_("Tab size (%)"), "float", 22.0, (12, 30, 0, None),
       N_("Size of the round tabs, as a percentage of a piece")),
      ("seed", N_("Variant"), "int", 1, (1, 9999), N_("Another number: the tabs point other ways")),
      ("outline", N_("Cut the outline"), "bool", True, None, N_("Cut the rectangle around the puzzle too"))],
     _puzzle),
    ("ruler", N_("Ruler"), "ruler",
     N_("Ruler: a mark every millimetre, numbers every centimetre"),
     [("length", N_("Length"), "float", 150.0, (10, 1000, 0, "mm"), N_("Length of the scale")),
      ("width", N_("Width"), "float", 25.0, (12, 100, 1, "mm"), N_("Width of the ruler")),
      ("unit", N_("Numbers in"), "choice", "cm", [("cm", "cm"), ("mm", "mm")],
       N_("The numbers count centimetres or millimetres")),
      ("numbers", N_("Numbers"), "bool", True, None, N_("Engrave the numbers")),
      ("outline", N_("Cut the outline"), "bool", True, None, N_("Cut the ruler out of the sheet"))],
     _ruler),
    ("qr", N_("QR code"), "qrcode",
     N_("QR code: a text or web address as a code to engrave (raster)"),
     [("text", N_("Text or address"), "text", "https://cyryllo.github.io/Kerfly/", None,
       N_("What the code holds, for example a web address")),
      ("size", N_("Size"), "float", 30.0, (8, 500, 1, "mm"), N_("Width of the code with its free border")),
      ("error", N_("Error correction"), "choice", "m",
       [("l", N_("Low (7 %)")), ("m", N_("Medium (15 %)")), ("q", N_("High (25 %)")), ("h", N_("Highest (30 %)"))],
       N_("How much of the code can be damaged and still read; more makes the code denser")),
      ("border", N_("Free border"), "int", 2, (0, 8), N_("Empty modules around the code (scanners need some)"))],
     _qr),
    ("test_card", N_("Test card"), "clipboard-check",
     N_("Test card: every operation on a piece of 3 mm plywood of about 160 × 100 mm, to check the laser: "
        "size (a 50 mm square with a 20 mm hole), a 100 mm ruler, raster, patterns, a hinge, text on a path, "
        "bridges"),
     [], _test_card),
]

from kerfly.gui import stamp as _stamp                 # noqa: E402

GENERATORS.insert(len(GENERATORS) - 1, (
    "stamp", N_("Stamp"), "rubber-stamp",
    N_("Stamp: text, a picture and a frame for a rubber stamp; the background is burnt away and the stamp is "
       "mirrored, so it prints the right way round"),
    _stamp.FIELDS, _stamp.make))
GENERATORS.insert(len(GENERATORS) - 1, (
    "round_stamp", N_("Round stamp"), "rosette",
    N_("Round stamp: text around the top and the bottom, rings, and text or a picture in the middle; burnt "
       "for rubber like the stamp"),
    _stamp.ROUND_FIELDS, _stamp.make_round))
# the button that makes the design (default: Insert)
ACCEPT_TEXT = {"stamp": N_("Generate stamp"), "round_stamp": N_("Generate stamp")}

# names of the generated elements (kerfly.core.generators), shown in the element list
ITEM_NAMES = [N_("Field"), N_("Label"), N_("Bottom"), N_("Front"), N_("Back"), N_("Left side"),
              N_("Right side"), N_("Lid"), N_("Comb"), N_("Comb cut"), N_("Slot plate"), N_("Gear"),
              N_("Axle hole"), N_("Puzzle cuts"), N_("Puzzle outline"), N_("Marks"), N_("Number"),
              N_("Ruler outline"), N_("Square 50 mm"), N_("Hole 20 mm"), N_("Ruler 100 mm"),
              N_("Raster block"), N_("Raster text"), N_("Pattern fill"), N_("Living hinge"), N_("Circle"),
              N_("Text on a path"), N_("Bridges"), N_("Pentagon"), N_("Open line"), N_("QR code"), N_("Stamp"),
              N_("Stamp outline")]


def generator(key):
    return next(g for g in GENERATORS if g[0] == key)


# ---------------------------------------------------------------- remembered numbers
def _settings():
    from PySide6.QtCore import QSettings
    from kerfly.core.materials import library_path
    return QSettings(os.path.join(os.path.dirname(library_path()), "window.ini"), QSettings.IniFormat)


def default_of(fields, name):
    return next(f[3] for f in fields if f[0] == name)


def defaults(fields, window):
    return {f[0]: (f[3](window) if callable(f[3]) else f[3]) for f in fields}


def load_values(key, fields, window):
    values = defaults(fields, window)
    try:
        s = _settings()
        s.beginGroup("generator_" + key)
        for name, _label, kind, default, _opt, _tip in fields:
            if s.contains(name):
                raw = s.value(name)
                if kind == "float":
                    values[name] = float(raw)
                elif kind == "int":
                    values[name] = int(float(raw))
                elif kind == "bool":
                    values[name] = str(raw).lower() in ("1", "true")
                else:
                    values[name] = str(raw)
        s.endGroup()
    except Exception:
        pass
    return values


def save_values(key, values):
    try:
        s = _settings()
        s.beginGroup("generator_" + key)
        for name, value in values.items():
            s.setValue(name, value)
        s.endGroup()
        s.sync()
    except Exception:
        pass


# ---------------------------------------------------------------- dialog
class GeneratorDialog(QDialog):
    """The numbers of one generator, with a preview of the design."""

    def __init__(self, window, key, remember=True):
        super().__init__(window)
        self.window_ = window
        self.key, title, _icon, tip, self.fields, self.make = generator(key)
        self.remember = remember
        self.setWindowTitle(_(title))
        values = load_values(key, self.fields, window) if remember else defaults(self.fields, window)
        self.widgets = {}
        form = QFormLayout()
        speed_unit = _speed_unit(window)
        len_unit = "mm"
        for name, label, kind, _default, opt, ftip in self.fields:
            value = values[name]
            if kind == "float":
                w = QDoubleSpinBox()
                lo, hi, decimals, unit = opt
                w.setRange(lo, hi)
                w.setDecimals(decimals)
                if unit == "speed":
                    w.setSuffix(" " + speed_unit)
                elif unit:
                    w.setSuffix(" " + (len_unit if unit == "mm" else unit))
                w.setValue(float(value))
                w.valueChanged.connect(self._changed)
            elif kind == "int":
                w = QSpinBox()
                w.setRange(*opt)
                w.setValue(int(value))
                w.valueChanged.connect(self._changed)
            elif kind == "choice":
                w = QComboBox()
                for data, text in opt:
                    w.addItem(_(text), data)
                w.setCurrentIndex(max(0, w.findData(value)))
                w.currentIndexChanged.connect(self._changed)
            elif kind == "bool":
                w = QCheckBox()
                w.setChecked(bool(value))
                w.toggled.connect(self._changed)
            elif kind == "multiline":
                w = QPlainTextEdit(_(value) if value == default_of(self.fields, name) else value)
                w.setFixedHeight(w.fontMetrics().lineSpacing() * 4 + 14)
                w.textChanged.connect(self._changed)
            elif kind == "font":
                w = QFontComboBox()
                from PySide6.QtGui import QFont
                w.setCurrentFont(QFont(str(value)))
                w.currentFontChanged.connect(self._changed)
            elif kind == "file":
                w = QWidget()
                row = QHBoxLayout(w)
                row.setContentsMargins(0, 0, 0, 0)
                edit = QLineEdit(str(value))
                edit.setPlaceholderText(_("none"))
                edit.textChanged.connect(self._changed)
                browse = QToolButton()
                browse.setText("…")
                browse.setToolTip(_("Choose a file"))
                browse.clicked.connect(lambda _c=False, e=edit: self._choose_file(e))
                row.addWidget(edit, 1)
                row.addWidget(browse)
                w.edit = edit
                from PySide6.QtWidgets import QSizePolicy
                w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            else:
                w = QLineEdit(_(value) if value and value == default_of(self.fields, name) else str(value))
                w.textChanged.connect(self._changed)
            w.setToolTip(_(ftip))
            w.setProperty("generator_field", name)
            lbl = QLabel(_(label))
            lbl.setToolTip(_(ftip))
            form.addRow(lbl, w)
            self.widgets[name] = w
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setMinimumSize(420, 320)
        self.view.setBackgroundBrush(QBrush(QColor("#e9ebef")))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        right = QVBoxLayout()
        right.addWidget(self.view, 1)
        right.addWidget(self.summary)
        top = QHBoxLayout()
        top.addLayout(form)
        top.addLayout(right, 1)
        info = QLabel(_(tip))
        info.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_(ACCEPT_TEXT.get(key, N_("Insert"))))
        for b in buttons.buttons():                    # Enter in a field updates the preview, it does not insert
            b.setAutoDefault(False)
            b.setDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(top, 1)
        layout.addWidget(buttons)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._preview)
        self._enable_fields()
        self._preview()

    def values(self):
        out = {}
        for name, _label, kind, _default, _opt, _tip in self.fields:
            w = self.widgets[name]
            if kind in ("float", "int"):
                out[name] = w.value()
            elif kind == "choice":
                out[name] = w.currentData()
            elif kind == "bool":
                out[name] = w.isChecked()
            elif kind == "multiline":
                out[name] = w.toPlainText()
            elif kind == "font":
                out[name] = w.currentFont().family()
            elif kind == "file":
                out[name] = w.edit.text().strip()
            else:
                out[name] = w.text()
        return out

    def _choose_file(self, edit):
        name, _unused = QFileDialog.getOpenFileName(self, _("Choose a picture"), os.path.dirname(edit.text()),
                                                    _("Pictures (*.png *.jpg *.jpeg *.bmp *.svg);;All files (*)"))
        if name:
            edit.setText(name)

    def result_design(self):
        return self.make(self.values(), self.window_)

    def _changed(self, *_args):
        self._enable_fields()
        self._timer.start()

    def _enable_fields(self):
        """Own width and height (diameter) only with the own size (a stamp's ready-made sizes)."""
        preset = self.widgets.get("preset")
        if preset is not None:
            own = preset.currentData() == "custom"
            for name in ("width", "height", "diameter"):
                if name in self.widgets:
                    self.widgets[name].setEnabled(own)

    def _preview(self):
        from kerfly.gui.text_shapes import update_text_spec
        self.scene.clear()
        try:
            design = self.result_design()
        except Exception as e:                    # a combination of numbers that makes no design
            self.summary.setText(str(e))
            return
        colors = {l.key: l.color for l in design.layers}
        xs, ys = [], []
        for item in design.items:
            if item.image is not None:                 # a picture (stamp): shown at its size
                from PySide6.QtGui import QPixmap
                pix = self.scene.addPixmap(QPixmap.fromImage(item.image))
                k = 25.4 / item.dpi
                pix.setTransformationMode(Qt.SmoothTransformation)
                pix.setScale(k)
                pix.setPos(item.left, item.top)
                xs += [item.left, item.left + item.image.width() * k]
                ys += [item.top, item.top + item.image.height() * k]
                continue
            spec = item.spec.copy()
            if spec.kind == "text":
                update_text_spec(spec)
            color = colors.get(item.layer) or DEFAULT_COLORS[gen.KIND_OF_OPERATION.get(spec.operation, "cut")]
            polys = outlines(spec)
            pts = [p for poly in polys for p in poly]
            if not pts:
                continue
            x0 = min(p[0] for p in pts)
            y0 = min(p[1] for p in pts)
            path = QPainterPath()
            for poly in polys:
                if len(poly) < 2:
                    continue
                path.moveTo(QPointF(poly[0][0] - x0 + item.left, poly[0][1] - y0 + item.top))
                for x, y in poly[1:]:
                    path.lineTo(QPointF(x - x0 + item.left, y - y0 + item.top))
            pen = QPen(QColor(color), 0)
            fill = QBrush(QColor(color)) if spec.operation == "fill" else QBrush(Qt.NoBrush)
            self.scene.addPath(path, pen, fill)
            r = path.boundingRect()
            xs += [r.left(), r.right()]
            ys += [r.top(), r.bottom()]
        if xs:
            rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-3, -3, 3, 3)
            self.scene.setSceneRect(rect)
            self.view.fitInView(rect, Qt.KeepAspectRatio)
            self.summary.setText(_("%(w).1f × %(h).1f mm, %(n)d shapes, %(l)d layers") % {
                "w": max(xs) - min(xs), "h": max(ys) - min(ys), "n": len(design.items), "l": len(design.layers)})

    def keyPressEvent(self, event):
        """Enter in a field takes the number and updates the preview; it does not insert
        (only the button does)."""
        from PySide6.QtWidgets import QAbstractButton
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not isinstance(self.focusWidget(), QAbstractButton):
            self._enable_fields()
            self._preview()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.scene.sceneRect().isEmpty():
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def accept(self):
        if self.remember:
            save_values(self.key, self.values())
        super().accept()
