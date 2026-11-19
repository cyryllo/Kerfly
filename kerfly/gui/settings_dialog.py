"""
Settings dialog, built from a declarative list of fields.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                               QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from kerfly.core.config import BOARD_NAMES, is_true
from kerfly.gui import icons, theme, widgets
from kerfly.i18n import LANGUAGES, N_, _

# (key, label, kind, options). kinds: bool, float, int, choice, path
TABS = [
    (N_("Machine"), [
        ("machine", N_("Machine"), "pairs", [("k40", N_("K40 (Lihuiyu board, USB)")),
                                             ("grbl", N_("GRBL board, serial port"))]),
        ("board_name", N_("Controller board"), "choice", BOARD_NAMES),
        ("usb_port", N_("USB port (beta)"), "usb_port", None),
        ("grbl_port", N_("GRBL: serial port"), "serial_port", None),
        ("grbl_baud", N_("GRBL: serial speed (baud)"), "choice", ["115200", "250000", "57600", "38400", "9600"]),
        ("gcode_s_max", N_("GRBL: full power S ($30)"), "int", (1, 100000)),
        ("grbl_jog", N_("GRBL: jog speed, arrows (mm/min)"), "float", (100, 30000, 0, None)),
        ("grbl_home_speed", N_("GRBL: homing speed ($25, mm/min; 0: the board's own)"), "float",
         (0, 30000, 0, None)),
        ("units", N_("Units"), "choice", ["mm", "in"]),
        ("LaserXsize", N_("Bed width"), "float", (1, 5000, 1, "len")),
        ("LaserYsize", N_("Bed height"), "float", (1, 5000, 1, "len")),
        # the corner the head homes to (one of them shown: a K40's or a GRBL laser's)
        ("HomeUR", N_("Home corner"), "corner_k40", None),
        ("grbl_home", N_("Home corner"), "corner_grbl", None),
        ("init_home", N_("Home the head when initializing"), "bool", None),
        ("post_home_xy", N_("Home the head after a job (back to 0, 0)"), "bool", None),
        ("post_home", N_("Unlock rail after a job"), "bool", None),
        ("post_beep", N_("Beep after a job"), "bool", None),
        ("post_disp", N_("Show a report after a job (its time; the program's output)"), "bool", None),
        ("pre_exec", N_("Run a program before a job"), "bool", None),
        ("pre_batch_path", N_("Program to run before a job"), "path",
         (N_("Program to run before a job"), N_("a program or script (.bat, .sh)"))),
        ("post_exec", N_("Run a program after a job"), "bool", None),
        ("batch_path", N_("Program to run after a job"), "path",
         (N_("Program to run after a job"), N_("a program or script (.bat, .sh)"))),
        ("LaserXscale", N_("X scale factor"), "float", (0.5, 2, 4, None)),
        ("LaserYscale", N_("Y scale factor"), "float", (0.5, 2, 4, None)),
        ("show_power", N_("M3 board: set power per operation"), "bool", None),
        ("max_power", N_("M3 board: maximum power (%)"), "float", (0, 100, 1, None)),
        ("materials_shared", N_("Share the material library of another laser (e.g. one of the same kind)"),
         "bool", None),
        ("materials_from", N_("The laser whose material library it uses"), "laser_choice", None),
    ]),
    (N_("Raster"), [
        ("halftone", N_("Halftone (dither) grayscale images"), "bool", None),
        ("dither", N_("Dithering method"), "dither", None),
        ("ht_size", N_("Halftone resolution (dpi)"), "choice", ["1000", "500", "333", "250", "200", "167", "143", "125"]),
        ("negate", N_("Invert raster colors"), "bool", None),
        ("mirror", N_("Mirror design"), "bool", None),
        ("rotate", N_("Rotate design 90°"), "bool", None),
        ("engraveUP", N_("Engrave bottom to top"), "bool", None),
        ("rast_step", N_("Scan line step (in)"), "float", (0.001, 0.063, 3, None)),
        ("bezier_M1", N_("Levels curve slope, dark end"), "float", (0, 10, 2, None)),
        ("bezier_M2", N_("Levels curve slope, light end"), "float", (0, 10, 2, None)),
        ("bezier_weight", N_("Levels curve weight"), "float", (0, 10, 2, None)),
    ]),
    (N_("Vector"), [
        ("inside_first", N_("Cut inside shapes first"), "bool", None),
        ("trace_w_laser", N_("Boundary trace with laser on"), "bool", None),
        ("Trace_power", N_("Boundary trace power"), "power", None),
        ("trace_rect", N_("Boundary trace as a rectangle (off: along the outline of the design)"), "bool", None),
        ("trace_gap", N_("Boundary trace gap"), "float", (0, 100, 1, "len")),
        ("trace_speed", N_("Boundary trace speed"), "float", (0.1, 1000, 1, "speed")),
    ]),
    (N_("View"), [
        ("grid_mm", N_("Snap grid (mm, 0 = off)"), "float", (0, 100, 1, None)),
        ("snap_objects", N_("Snap to other objects"), "bool", None),
        ("follow_head", N_("The design follows the laser head"), "bool", None),
        ("kind_buttons", N_("Engrave, Outline and Cut buttons next to Start (each runs only its layers)"),
         "bool", None),
        ("theme", N_("Theme (applies after restart)"), "theme", None),
    ]),
    (N_("Rotary"), [
        ("rotary", N_("Rotary attachment in use"), "bool", None),
        ("LaserRscale", N_("Rotary scale factor"), "float", (0.01, 100, 4, None)),
        ("rapid_feed", N_("Rotary rapid speed (0 = default)"), "float", (0, 1000, 1, "speed")),
    ]),
    (N_("Advanced"), [
        ("language", N_("Language (applies after restart)"), "language", None),
        ("check_updates", N_("Check once a day for a new version (asks GitHub; nothing about you is sent)"),
         "bool", None),
        ("use_inkscape", N_("Use Inkscape for SVG files when installed (otherwise built-in)"), "bool", None),
        ("inkscape_path", N_("Inkscape executable"), "path", (N_("Inkscape executable"), N_("found automatically"))),
        ("ink_timeout", N_("Inkscape timeout (minutes)"), "float", (0.1, 60, 1, None)),
        ("reduced_mem", N_("Reduced memory use (500 dpi raster)"), "bool", None),
        ("pre_pr_crc", N_("Prepare USB data before sending"), "bool", None),
        ("wait", N_("Wait for the laser to finish"), "bool", None),
        ("t_timeout", N_("USB timeout (ms)"), "int", (10, 10000)),
        ("n_timeouts", N_("USB retries"), "int", (1, 1000)),
    ]),
]

# the pages' sections (docs/ui-mockups/Settings): the field a section starts with -> its title
SECTIONS = {
    "machine": N_("Controller"), "units": N_("Work area"), "init_home": N_("Homing and the end of a job"),
    "pre_exec": N_("Programs run with a job"), "LaserXscale": N_("Scale"), "show_power": N_("Power (M3 board)"),
    "halftone": N_("Halftone"), "negate": N_("Picture"), "rast_step": N_("Scan lines and levels"),
    "inside_first": N_("Cutting"), "trace_w_laser": N_("Boundary trace"),
    "grid_mm": N_("Bed view"), "theme": N_("Look"),
    "rotary": N_("Rotary attachment"),
    "language": N_("Program"), "use_inkscape": N_("Inkscape"), "reduced_mem": N_("Memory and USB"),
}
# the pages' icons in the category list
PAGE_ICONS = {"Machine": "laser", "Raster": "grid-dots", "Vector": "vector", "View": "zoom-scan",
              "Rotary": "rotate-clockwise-2", "Advanced": "settings-2"}

M3_BOARD = "LASER-M3"           # the only board with power control
GRBL_KEYS = ("grbl_port", "grbl_baud", "grbl_home", "grbl_jog", "grbl_home_speed", "gcode_s_max")    # only for a GRBL machine
# a GRBL laser's home corner: its setting -> the corner (of CornerPicker)
GRBL_CORNERS = {"lower_left": "LL", "upper_left": "UL", "upper_right": "UR", "lower_right": "LR"}
K40_KEYS = ("board_name", "usb_port", "HomeUR")                                  # only for a K40

# field -> the tick it depends on
DEPENDS = {"materials_from": "materials_shared", "dither": "halftone", "Trace_power": "trace_w_laser", "batch_path": "post_exec", "pre_batch_path": "pre_exec", "LaserRscale": "rotary",
           "rapid_feed": "rotary"}

# settings whose change invalidates the computed raster lines / path order
RASTER_KEYS = {"halftone", "dither", "ht_size", "negate", "mirror", "rotate", "rast_step", "bezier_M1",
               "bezier_M2", "bezier_weight", "LaserXscale", "LaserYscale", "LaserRscale", "rotary"}
RELOAD_KEYS = {"inside_first", "reduced_mem", "use_inkscape"}


def _is_machine(key):
    from kerfly.core.profiles import MACHINE_KEYS
    return key in MACHINE_KEYS


def form_pages(machine):
    """[(title, [fields])] of the program's settings (machine False: one page per category, the units with
    the view), or of a laser's (machine True: one page, its fields in TABS' order)."""
    if machine:
        return [(N_("Laser"), [f for _t, fields in TABS for f in fields if _is_machine(f[0])])]
    pages = []
    units = [f for _t, fields in TABS for f in fields if f[0] == "units"]
    for title, fields in TABS:
        mine = [f for f in fields if not _is_machine(f[0]) and f[0] != "units"]
        if title == "View":
            mine = units + mine
        if mine:
            pages.append((title, mine))
    return pages


# a section's title where the two forms differ from SECTIONS (the program's units, a laser's work area, ...)
PROGRAM_SECTIONS = {"units": N_("Units"), "reduced_mem": N_("Memory")}
MACHINE_SECTIONS = {"LaserXsize": N_("Work area"), "pre_pr_crc": N_("USB connection"),
                    "grbl_jog": N_("Head movement"), "materials_shared": N_("Material library")}


class SettingsForm(QWidget):
    """The fields of the program's settings (in categories) or of a laser's (one scrolling page), built from
    TABS: their values in and out (result_values), the fields that count only with a tick greyed out."""

    def __init__(self, values, machine=False, window=None, tab=0, parent=None):
        super().__init__(parent)
        self.values = dict(values)
        self.window_ = window
        self.machine = machine
        self._getters = {}
        self._widgets = {}
        self._labels = {}
        units = self.values.get("units", "mm")
        len_unit = units
        from kerfly.core.config import speed_factor, speed_unit as _speed_unit
        speed_unit = _speed_unit(self.values)
        self.speed_factor = speed_factor(self.values)        # shown = kept x it (mm/min of a GRBL machine)
        sections = dict(SECTIONS, **(MACHINE_SECTIONS if machine else PROGRAM_SECTIONS))
        pages = form_pages(machine)
        # (docs/ui-mockups/Settings) the categories in a list on the left, their page on the right in sections,
        # each page scrolling up and down on its own; a laser's settings: one page
        self.categories = QListWidget()
        self.categories.setObjectName("settings_categories")
        self.categories.setFixedWidth(2 * theme.OPTION_TITLE - theme.SPACE_L)
        self.categories.setIconSize(QSize(theme.ICON, theme.ICON))
        self.pages = QStackedWidget()
        fm = self.fontMetrics()
        # one label column width for every page, so fields line up when switching pages
        label_width = max(fm.horizontalAdvance(_(label)) for _t, fields in pages
                          for _k, label, kind, _o in fields if kind != "bool") + theme.SPACE_L
        for title, fields in pages:
            page = QWidget()
            v = QVBoxLayout(page)
            v.setContentsMargins(0, 0, theme.SPACE_L, 0)
            v.setSpacing(theme.PAD_DIALOG)
            section = None
            row = 0
            for key, label, kind, opt in fields:
                if section is None or key in sections:
                    section = widgets.Section(_(sections[key]) if key in sections else None)
                    section.grid.setColumnStretch(0, 0)
                    section.grid.setColumnMinimumWidth(0, label_width)
                    section.grid.setColumnStretch(2, 1)
                    v.addWidget(section)
                    row = 0
                grid = section.grid
                widget, getter = self._make_field(key, kind, opt, len_unit, speed_unit)
                widget.setProperty("setting_key", key)      # which setting it is (tests find it by this)
                if kind == "bool":
                    widget.setText(_(label))          # the text sits right next to the box
                    grid.addWidget(widget, row, 0, 1, 3)
                else:
                    self._labels[key] = widgets.hint(_(label), wrap=False)
                    grid.addWidget(self._labels[key], row, 0)
                    span = 2 if kind == "path" else 1
                    grid.addWidget(widget, row, 1, 1, span)
                self._getters[key] = getter
                self._widgets[key] = widget
                row += 1
            v.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidget(page)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.pages.addWidget(scroll)
            self.categories.addItem(QListWidgetItem(icons.tabler(PAGE_ICONS.get(title, "settings")), _(title)))
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.categories.setCurrentRow(min(tab, self.pages.count() - 1))
        # as wide as the widest page (they scroll only up and down)
        self.pages.setMinimumWidth(max(self.pages.widget(i).widget().minimumSizeHint().width()
                                       for i in range(self.pages.count()))
                                   + self.pages.widget(0).verticalScrollBar().sizeHint().width())
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.PAD_DIALOG)
        if not machine:
            row.addWidget(self.categories)
        else:
            self.categories.hide()
        row.addWidget(self.pages, 1)
        tips = {"grbl_jog": _("How fast the head moves with the arrows and the corner buttons (a GRBL laser; a "
                              "K40's board moves at its own speed)"),
                "grbl_home_speed": _("How fast the head looks for its home switches: written into the GRBL board "
                                     "($25, kept in its memory) when Kerfly connects; 0 leaves the board's own. A "
                                     "K40 homes at its board's own speed"),
                "Trace_power": _("Laser power during the boundary trace, in per cent of the laser's maximum "
                                 "power. Used by M3 boards with power per operation; on other boards the power "
                                 "knob of the laser sets it"),
                "batch_path": _("Started after every finished job, for example to switch off "
                                "the exhaust or send a message; its output goes to the report"),
                "pre_batch_path": _("Started before every job sent to the laser, for example "
                                    "to switch on the exhaust or the air pump; the job waits "
                                    "until it ends (at most a minute)")}
        for key, tip in tips.items():
            if key in self._widgets:
                self._widgets[key].setToolTip(tip)
        # fields that count only with a tick: greyed out without it (as in K40 Whisperer)
        for switch in set(DEPENDS.values()) | {"show_power"}:
            if switch in self._widgets:
                self._widgets[switch].toggled.connect(self._update_enabled)
        if "board_name" in self._widgets:
            self._widgets["board_name"].currentTextChanged.connect(self._update_enabled)
            self._widgets["machine"].currentIndexChanged.connect(self._update_enabled)
        self._update_enabled()

    def page_of(self, widget):
        """The number of the page (category) a field is on."""
        return next(i for i in range(self.pages.count()) if self.pages.widget(i).isAncestorOf(widget))

    def show_page(self, index):
        self.categories.setCurrentRow(index)

    def _update_enabled(self, *_args):
        """Fields that count only with a tick, and the power settings only with the M3 board (the other
        boards have no power control: the knob of the laser sets it): greyed out otherwise."""
        wanted = {key: self._widgets[switch].isChecked() for key, switch in DEPENDS.items()
                  if key in self._widgets and switch in self._widgets}
        if "machine" in self._widgets:                    # a laser's settings
            grbl = self._widgets["machine"].currentData() == "grbl"
            m3 = self._widgets["board_name"].currentText() == M3_BOARD and not grbl
            for key in GRBL_KEYS:
                wanted[key] = grbl
            for key in K40_KEYS:
                wanted[key] = not grbl
            wanted["show_power"] = m3
            wanted["max_power"] = m3 and self._widgets["show_power"].isChecked()
            wanted["Trace_power"] = wanted["Trace_power"] and (m3 or grbl)     # GRBL: S, always
        else:
            m3 = True
        for key, on in wanted.items():
            for part in [self._widgets[key]] + ([self._labels[key]] if key in self._labels else []):
                part.setEnabled(on)
        if "machine" in self._widgets:                    # one home corner shown: the chosen machine's
            for key, on in (("HomeUR", not grbl), ("grbl_home", grbl)):
                for part in (self._widgets[key], self._labels[key]):
                    part.setVisible(on)
        if "show_power" in self._widgets:
            tip = "" if m3 else _("Only the M3 board sets the power; on other boards the power knob of the laser "
                                  "does")
            for key in ("show_power", "max_power"):
                self._widgets[key].setToolTip(tip)

    def _make_field(self, key, kind, opt, len_unit, speed_unit):
        value = self.values.get(key, "")
        if kind in ("corner_k40", "corner_grbl"):
            tips = {"UL": _("Upper left"), "UR": _("Upper right"), "LL": _("Lower left"), "LR": _("Lower right")}
            if kind == "corner_k40":                # a K40: HomeUR (the right side, mirrors the data) and home_lower
                lower = is_true(self.values.get("home_lower", "0"))
                w = widgets.CornerPicker(("L" if lower else "U") + ("R" if is_true(value) else "L"), None, tips)
                getter = lambda: "1" if w.current()[1] == "R" else "0"     # noqa: E731
                self._getters["home_lower"] = lambda: "1" if w.current()[0] == "L" else "0"
            else:
                w = widgets.CornerPicker(GRBL_CORNERS.get(value or "lower_left", "LL"), None, tips)
                getter = lambda: {c: n for n, c in GRBL_CORNERS.items()}[w.current()]     # noqa: E731
            w.setToolTip(_("The corner of the bed the head goes to on Home. Place design at the head and Design "
                           "follows the head bring the same corner of the design to the head"))
            return w, getter
        if kind == "pairs":
            w = QComboBox()
            for code, name in opt:
                w.addItem(_(name), code)
            w.setCurrentIndex(max(0, w.findData(value)))
            return w, lambda: w.currentData()
        if kind == "serial_port":
            from kerfly.core import grbl
            from kerfly.gui import icons
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            combo = QComboBox()

            def fill():
                current = combo.currentData() if combo.count() else value
                combo.clear()
                combo.addItem(_("The first GRBL board that answers"), "")
                for device, description in grbl.serial_ports():
                    combo.addItem("%s (%s)" % (device, description) if description != device else device, device)
                if current and combo.findData(current) < 0:
                    combo.addItem(_("%s (not plugged in now)") % current, current)
                combo.setCurrentIndex(max(0, combo.findData(current)))
            fill()
            combo.setToolTip(_("The serial port of the GRBL board (Linux: /dev/ttyUSB0 or /dev/ttyACM0; Windows: "
                               "COM3, ...), kept in this laser's profile"))
            again = QPushButton(icons.tabler("refresh"), "")
            again.setToolTip(_("Look for serial ports again (after plugging the laser in)"))
            again.clicked.connect(fill)
            row.addWidget(combo, 1)
            row.addWidget(again)
            self.serial_port_box = combo
            return box, lambda: combo.currentData() or ""
        if kind == "laser_choice":
            # the other lasers with a material library of their own (no chains of shared libraries)
            w = QComboBox()
            profiles = getattr(self.window_, "profiles", None)
            own = self.values.get("laser_id", "")
            for name, s in (profiles.items if profiles is not None else []):
                if s.get("laser_id") and s.get("laser_id") != own and not is_true(s.get("materials_shared", "0")):
                    w.addItem(name, s["laser_id"])
            if not w.count():
                w.addItem(_("(no other laser with a library of its own)"), "")
            w.setCurrentIndex(max(0, w.findData(value)))
            w.setToolTip(_("Lasers of the same kind can use one material library: changes to it count for "
                           "all of them"))
            return w, lambda: w.currentData() or ""
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(is_true(value))
            return w, lambda: "1" if w.isChecked() else "0"
        if kind == "language":
            w = QComboBox()
            w.addItem(_("System default"), "")
            for code, name in LANGUAGES.items():
                w.addItem(name, code)
            index = w.findData(value)
            w.setCurrentIndex(max(0, index))
            return w, lambda: w.currentData()
        if kind == "usb_port":
            from kerfly.core import usbports
            from kerfly.gui import icons
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            combo = QComboBox()
            combo.addItem(_("The first K40 found"), "")
            ports = usbports.list_lasers()
            for p in ports:
                combo.addItem(p.label, p.key)
            if value and combo.findData(value) < 0:
                combo.addItem(_("%s (not plugged in now)") % value, value)
            combo.setCurrentIndex(max(0, combo.findData(value)))
            combo.setToolTip(_("With two lasers plugged into this computer: the USB port of this laser's board, "
                               "kept in its profile (beta: not yet checked with two lasers)"))
            which = QPushButton(icons.tabler("arrows-horizontal"), _("Which one?"))
            which.setToolTip(_("The head of the laser on the chosen port moves a little to the right and back"))
            parent = self.window_

            def identify():
                port = usbports.find(ports, combo.currentData())
                if port is None:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.information(self, _("USB port"), _("Choose a laser that is plugged in now."))
                    return
                from kerfly.gui.usb_port_dialog import identify as _identify
                _identify(self, parent.laser, port)
            which.clicked.connect(identify)
            which.setEnabled(bool(ports) and parent is not None and hasattr(parent, "laser"))
            row.addWidget(combo, 1)
            row.addWidget(which)
            self.usb_port_box = combo
            return box, lambda: combo.currentData() or ""
        if kind == "dither":
            from kerfly.core.dither import DEFAULT, METHODS
            w = QComboBox()
            for code, name in METHODS:
                w.addItem(_(name), code)
            w.setCurrentIndex(max(0, w.findData(value or DEFAULT)))
            w.setToolTip(_("How a grayscale picture becomes laser dots. Floyd-Steinberg: the classic one (default). "
                           "Atkinson: more contrast, clean light areas (wood). Jarvis, Stucki, Burkes, Sierra: "
                           "smoother gradients. Ordered (Bayer): an even, regular texture. Threshold: black "
                           "and white only"))
            return w, lambda: w.currentData()
        if kind == "theme":
            from kerfly.gui.theme import DEFAULT, THEMES
            w = QComboBox()
            for code, name in THEMES:
                w.addItem(_(name), code)
            w.setCurrentIndex(max(0, w.findData(value or DEFAULT)))
            return w, lambda: w.currentData()
        if kind == "choice":
            w = QComboBox()
            w.addItems(opt)
            if value not in opt:
                w.addItem(str(value))
            w.setCurrentText(str(value))
            return w, w.currentText
        if kind == "int":
            w = QSpinBox()
            w.setRange(*opt)
            w.setValue(int(float(value or 0)))
            return w, lambda: str(w.value())
        if kind == "float":
            lo, hi, decimals, unit = opt
            f = self.speed_factor if unit == "speed" else 1.0
            w = QDoubleSpinBox()
            w.setRange(lo * f, hi * f)
            w.setDecimals(decimals if f == 1 else 0)
            if unit == "len":
                w.setSuffix(" " + len_unit)
            elif unit == "speed":
                w.setSuffix(" " + speed_unit)
            try:
                w.setValue(float(value) * f)
            except ValueError:
                pass
            if f != 1:
                return w, lambda: ("%." + str(decimals + 2) + "f") % (w.value() / f)
            return w, lambda: ("%." + str(decimals) + "f") % w.value()
        if kind == "power":                     # a fraction of the maximum power, shown in per cent
            w = QDoubleSpinBox()
            w.setRange(0, 100)
            w.setDecimals(0)
            w.setSuffix(" %")
            try:
                w.setValue(float(value) * 100.0)
            except ValueError:
                pass
            return w, lambda: "%.2f" % (w.value() / 100.0)
        if kind == "path":
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            title, placeholder = opt
            edit = QLineEdit(str(value))
            edit.setPlaceholderText(_(placeholder))
            edit.setMinimumWidth(edit.fontMetrics().averageCharWidth() * 36)
            browse = QPushButton(_("Browse…"))

            def pick():
                name, _unused = QFileDialog.getOpenFileName(self, _(title), edit.text())
                if name:
                    edit.setText(name)
            browse.clicked.connect(pick)
            row.addWidget(edit)
            row.addWidget(browse)
            return box, edit.text
        raise ValueError(kind)

    def result_values(self):
        """(new values, set of changed keys)."""
        new = dict(self.values)
        changed = set()
        for key, getter in self._getters.items():
            val = getter()
            if str(self.values.get(key, "")) != val:
                # numeric fields: ignore pure formatting differences
                try:
                    if float(self.values.get(key, "nan")) == float(val):
                        continue
                except ValueError:
                    pass
                new[key] = val
                changed.add(key)
        return new, changed


class SettingsDialog(QDialog):
    """Settings → Settings…: the program's settings (a laser's are in Settings → Lasers…)."""

    def __init__(self, values, parent=None, tab=0):
        super().__init__(parent)
        self.setWindowTitle(_("Settings"))
        self.form = SettingsForm(values, machine=False, window=parent, tab=tab)
        body = widgets.DialogBody()
        body.add(self.form, 1)
        footer = widgets.DialogFooter(_("Save"))
        footer.info.setText(_("The program's settings; a laser's are in Settings → Lasers…"))
        footer.connect(self)
        widgets.dialog_layout(self, body, footer)
        self.resize(theme.DIALOG_LARGE + 80, theme.DIALOG_LARGE - 160)

    def __getattr__(self, name):
        # the form's fields and ways (values, _widgets, page_of, result_values, ...), as the dialog's own
        form = self.__dict__.get("form")
        if form is None:
            raise AttributeError(name)
        return getattr(form, name)
