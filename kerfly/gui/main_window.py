"""
Kerfly main window.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math
import os
import re
from dataclasses import replace

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer
from PySide6.QtCore import QLocale
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDockWidget, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QSpinBox, QTabWidget, QToolBar, QToolButton,
                               QVBoxLayout, QWidget, QFrame, QSizePolicy)

from kerfly import __version__
from kerfly.core import config, egvfile, job, loaders
from kerfly.gui.sizing import chars_width, fit_spin, refit_spin
from kerfly.i18n import C_, N_, _, ngettext, tr_message
from kerfly.core.config import is_true
from kerfly.core.design import Design
from kerfly.core.estimate import format_time
from kerfly.core.grbl import GrblController
from kerfly.core.laser import LaserController, LaserError, clamp_head_position, corner_offset
from kerfly.core import materials as material_lib
from kerfly.core import project as project_io
from kerfly.core.layers import (CUT, ENGRAVE, EXTRA_COLORS, GCODE, KINDS, RASTER, Layer, layer_of,
                                layer_times, part_present)
from kerfly.core.diag import log as diag_log
from kerfly.core.layout import (Element, align, compile_layout, distribute, mirror, mirror_about, on_bed,
                                rotate_about, selection_bounds, units)
from kerfly.core.shapes import ShapeSpec, build_design, outlines
from kerfly.gui import icons, theme, widgets
from kerfly.gui.image_dialog import ImageSizeDialog
from kerfly.gui.svg_render import render_svg
from kerfly.gui.text_shapes import update_text_spec
from kerfly.gui.tool_options import (KIND_NAMES, NEW_KIND_TITLES, ToolOptionsBar, option_field, option_title,
                                    ribbon_separator)
from kerfly.gui.preview import PreviewView
from kerfly.gui.settings_dialog import RASTER_KEYS, RELOAD_KEYS, SettingsDialog
from kerfly.gui.layers_panel import KIND_NAMES as LAYER_KIND_NAMES
from kerfly.core.layers import DEFAULT_COLORS as DEFAULT_LAYER_COLORS
from kerfly.gui.layers_panel import LayersPanel
from kerfly.gui.materials_dialog import MaterialsDialog
from kerfly.gui.worker import EgvSendWorker, GrblJobWorker, JobWorker, LayersJobWorker, RasterLayersWorker

# jog pad: 3 rows as tall as the machine column beside it (4 buttons of 56 px, spacing 4)
# the jog pad's buttons: its three rows as tall as the column of the four machine buttons beside it
JOG_BUTTON = (4 * theme.HEIGHT_ACTION + 3 * theme.SPACE_S - 2 * theme.SPACE_S) // 3
JOG_ICON = theme.ICON_LARGE
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*$")   # progress percentage at the end of a message
IMAGE_PATTERNS = " ".join("*" + e for e in loaders.IMAGE_EXTENSIONS)


def design_filters():
    return ";;".join([_("Projects and designs") + " (*.kerfly *.svg *.dxf *.ngc *.gcode *.nc *.g *.tap %s)"
                      % IMAGE_PATTERNS,
                      _("Kerfly projects") + " (*.kerfly)",
                      _("SVG files") + " (*.svg)", _("DXF files") + " (*.dxf)",
                      _("Images") + " (%s)" % IMAGE_PATTERNS,
                      _("G-code files") + " (*.ngc *.gcode *.nc *.g *.tap)",
                      _("All files") + " (*)"])



# default layers are bound to the K40 Whisperer settings (k40_whisperer.txt)
DEFAULT_LAYER_KEYS = {RASTER: ("include_Reng", "Reng_feed", "Reng_passes", "Reng_power"),
                      ENGRAVE: ("include_Veng", "Veng_feed", "Veng_passes", "Veng_power"),
                      CUT: ("include_Vcut", "Vcut_feed", "Vcut_passes", "Vcut_power"),
                      GCODE: ("include_Gcde", None, "Gcde_passes", "Gcode_power")}
OPERATION_KIND = {"cut": CUT, "engrave": ENGRAVE, "hatch": ENGRAVE, "fill": RASTER}


def _num(value, decimals=1):
    """Number formatted for the current language (e.g. 12,5 in Polish)."""
    return QLocale().toString(float(value) + 0.0, "f", decimals)


def _num_text(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


# the smallest window (a 1366 x 768 laptop screen still fits it)
MIN_WIDTH, MIN_HEIGHT = 1024, 680


class MainWindow(QMainWindow):
    def __init__(self, values):
        super().__init__()
        from kerfly.gui import wheelguard
        wheelguard.install()            # the wheel changes a field only after it was clicked
        self.values = values
        self.elements = []              # design elements placed on the bed
        self.group_names = {}           # group id -> its name (a generator's design, a sheet of a box)
        self.selected = None            # selected element
        self._compiled = None           # cached (design, origin) compiled from the elements
        self.layers = []                # layers; the first of each kind is the default one
        self._default_layer = {}        # kind -> default layer
        self._layer_cache = {}          # layer id -> compiled design (kept until the layout changes)
        self.materials = []             # the material library of the laser in use (after the profiles)
        self._init_layers()
        self.project_file = ""          # current .kerfly file
        self._dirty = False             # unsaved changes
        self._undo = []                 # layout snapshots for undo / redo
        self._redo = []
        self.design_file = ""           # last file opened (start folder for file dialogs)
        self.laser = self._make_laser()
        self.head = (0.0, 0.0)          # laser head position on the bed, inches (y <= 0)
        self.worker = None
        self._paused = False
        self._unit_widgets = []         # (spinbox, kind, key, sign) to update when units change
        from kerfly.core import profiles as profiles_core
        # the lasers (one in use); the app puts the profile in use into values before the window
        self.profiles = profiles_core.load_or_create(self.values, _("My laser"))
        # the laser in use's id and library choice in the window's values (the app puts the whole profile in;
        # without it, saving the profile would lose the id of its material library)
        current = self.profiles.get(self.profiles.current)
        for key in ("laser_id", "materials_shared", "materials_from"):
            if key in current and self.values.get(key) != current[key]:
                self.values[key] = current[key]
        self._load_materials()

        self._update_title()
        self.resize(1200, 780)                  # replaced by the saved / screen-based size in show()
        # smaller than this the panels squeeze the bed into a strip (a user asked for a minimum);
        # a smaller screen gets its whole available area as the minimum
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None
        self.setMinimumSize(min(MIN_WIDTH, area.width()) if area else MIN_WIDTH,
                            min(MIN_HEIGHT, area.height() - 40) if area else MIN_HEIGHT)
        self.preview = PreviewView()
        self.preview.snap_objects = is_true(self.values.get("snap_objects", "1"))
        self.tool_options = ToolOptionsBar()
        self.tool_options.changed.connect(self._tool_options_changed)
        self.tool_options.node_action.connect(lambda code: self.preview.node_editor.action(code))
        self.tool_options.offset_changed.connect(self._offset_values_changed)
        self.tool_options.crop_changed.connect(self._crop_values_changed)
        self.tool_options.offset_apply.connect(self.offset_selected)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        # the options bar (docs/ui-mockups/OptionBars): two rows of HEIGHT_OPTION_ROW across the window under
        # the ribbon; the first is always the selection (position, size, rotation, layer: _build_panel), the
        # second what is edited (the tool_options bar). On a narrow screen the rows scroll sideways together
        # instead of making the window wider than the screen.
        self.top_bar = QWidget()
        self.top_bar.setObjectName("top_bar")
        self.top_bar.setAttribute(Qt.WA_StyledBackground, True)
        bar_scroll = QScrollArea()
        bar_scroll.setObjectName("top_bar_scroll")
        bar_scroll.setFrameShape(QFrame.NoFrame)
        bar_scroll.setWidgetResizable(True)
        bar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        inner = QWidget()
        rows = QVBoxLayout(inner)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        self.selection_row = QWidget()
        self.tools_row = QWidget()
        for row in (self.selection_row, self.tools_row):
            row.setFixedHeight(theme.HEIGHT_OPTION_ROW)
            h = QHBoxLayout(row)
            h.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_L, 0)
            h.setSpacing(theme.SPACE_M)
            rows.addWidget(row)
        self.tools_row.layout().addWidget(self.tool_options, 1)
        bar_scroll.setWidget(inner)
        outer = QHBoxLayout(self.top_bar)
        outer.setContentsMargins(0, 0, 0, 1)            # the bottom line of the bar
        outer.addWidget(bar_scroll)
        self.top_bar_scroll = bar_scroll
        # as tall as the two rows, and the sideways scroll bar only while it is shown
        scroll_bar = bar_scroll.horizontalScrollBar()

        def fit_height(_lo=0, hi=0):
            try:
                extra = scroll_bar.sizeHint().height() if hi > 0 else 0
                self.top_bar.setFixedHeight(2 * theme.HEIGHT_OPTION_ROW + 1 + extra)
            except RuntimeError:
                pass                                 # the window is being closed
        scroll_bar.rangeChanged.connect(fit_height)
        fit_height(0, 0)
        # "a new version is available" (hidden until a check finds one)
        from kerfly.gui.update_check import UpdateBar
        self.update_bar = UpdateBar()
        self.update_bar.skip.connect(self._skip_update)
        central_layout.addWidget(self.update_bar)
        central_layout.addWidget(self.preview, 1)
        self.setCentralWidget(central)
        self.shape_defaults = {kind: ShapeSpec(kind=kind, operation="fill" if kind == "text" else "cut",
                                               text=_("Text"))
                               for kind in ("rectangle", "ellipse", "polygon", "line", "polyline", "text")}
        self.shape_defaults["pen"] = ShapeSpec(kind="path", operation="cut")
        self.shape_defaults["freehand"] = self.shape_defaults["pen"]
        # Text on a path tool: the text it puts on the clicked shape
        self.shape_defaults["textpath"] = ShapeSpec(kind="text", operation="engrave", text=_("Text"))
        self.preview.signals.drawn.connect(self._preview_drawn)
        self.preview.signals.selected.connect(self._preview_selected)
        self.preview.signals.hovered.connect(self._show_path)
        self.preview.signals.polyline_drawn.connect(self._preview_polyline_drawn)
        self.preview.signals.nodes_changed.connect(self._nodes_changed)
        self.preview.signals.pen_drawn.connect(self._preview_pen_drawn)
        self.preview.signals.edit_nodes.connect(self._edit_nodes_of)
        self.preview.signals.node_selection.connect(self._node_selection_changed)
        self.preview.signals.measured.connect(self._preview_measured)
        self.preview.signals.shape_picked.connect(self._shape_picked)
        self.preview.signals.context_menu.connect(self._bed_context_menu)
        # what the Fill tool gives to the shapes it is clicked on
        self.fill_defaults = ShapeSpec(kind="rectangle", fill_pattern="lines", fill_spacing=2.0)
        # what the Living hinge tool gives to the shapes it is clicked on
        self.hinge_defaults = ShapeSpec(kind="rectangle", hinge_pattern="straight")
        # the Offset tool: what a click on a shape (or "Offset selected") does
        self.offset_defaults = {"offset_distance": 2.0, "offset_join": "round", "offset_keep": True}
        self.nest_defaults = {"method": "rectangles", "gap": 2.0, "turn": True, "seconds": 10}
        self.crop_defaults = {"crop_shape": "rect"}
        self.preview.node_points_provider = self._node_points
        self.preview.signals.moved.connect(self._preview_moved)
        self.preview.signals.scaled.connect(self._preview_scaled)
        self.preview.signals.stretched.connect(self._preview_stretched)
        # the node tool ends with a click on the empty bed: back to Select
        self.preview.signals.leave_nodes.connect(lambda: self.tool_actions["select"].trigger())
        self.preview.signals.rotated.connect(self._preview_rotated)
        self.preview.signals.nudged.connect(self._preview_nudged)
        self._build_actions()
        # the options bar across the window, under the ribbon (over the left panel too)
        self.addToolBarBreak(Qt.TopToolBarArea)
        options = QToolBar(_("Options bar"))
        options.setObjectName("options_toolbar")
        options.setMovable(False)
        options.setFloatable(False)
        self.top_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        options.addWidget(self.top_bar)
        self.addToolBar(Qt.TopToolBarArea, options)
        self.options_toolbar = options
        self._build_tool_strip()
        self._build_panel()
        self._build_status()
        QTimer.singleShot(0, self._fit_panel_width)    # again once shown: the style sheet's fonts and padding
        self._update_power_visibility()
        self._update_laser_state()
        self.refresh_preview(fit=True)

    # ------------------------------------------------------------ UI setup
    def _action(self, text, slot, shortcut=None, tip=None):
        act = QAction(text, self)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        if tip:
            act.setStatusTip(tip)
        return act

    def _build_actions(self):
        self.act_new = self._action(_("&New project"), self.new_project, "Ctrl+N",
                                    _("Start an empty project: clears the bed (asks to save changes first)"))
        self.act_open = self._action(_("&Open design\u2026"), self.open_design, "Ctrl+O",
                                     _("Open a file, replacing everything on the bed"))
        self.act_reload = self._action(_("&Reload design"), self.reload_design, "F5")
        self.act_add = self._action(_("&Add design…"), self.add_design, "Ctrl+Shift+O",
                                    _("Add another file to the laser bed"))
        self.act_delete = self._action(_("&Delete element"), self.delete_selected, "Delete")
        self.act_delete.setShortcutContext(Qt.WidgetWithChildrenShortcut)   # only in the bed view
        self.preview.addAction(self.act_delete)
        self.act_undo = self._action(_("&Undo"), self.undo, "Ctrl+Z")
        self.act_redo = self._action(_("&Redo"), self.redo, "Ctrl+Shift+Z")
        self.act_duplicate = self._action(_("D&uplicate element"), self.duplicate_selected, "Ctrl+D")
        # the clipboard, as in Inkscape (text fields keep their own Ctrl+C / Ctrl+V while typing)
        self.act_copy = self._action(_("&Copy"), self.copy_selected, "Ctrl+C",
                                     _("Copy the selected elements, to paste them here or in another project"))
        self.act_cut = self._action(_("Cu&t"), self.cut_selected, "Ctrl+X",
                                    _("Copy the selected elements and remove them"))
        self.act_paste = self._action(_("&Paste"), lambda: self.paste(False), "Ctrl+V",
                                      _("Paste the copied elements at the mouse pointer (or next to where they were)"))
        self.act_paste_in_place = self._action(_("Paste in pla&ce"), lambda: self.paste(True), "Ctrl+Alt+V",
                                               _("Paste the copied elements exactly where they were"))
        self.act_select_all = self._action(_("Select &all"), self.select_all, "Ctrl+A",
                                           _("Select every element on the bed"))
        self.act_deselect = self._action(_("D&eselect"), self.deselect, "Ctrl+Shift+A",
                                         _("Select nothing (Esc on the bed does it too)"))
        self._clipboard = None          # copies of the elements and the names of their layers
        self._paste_count = 0
        self.act_order = {}
        # the element list is the order of the job: the laser does the top element first
        for how, text, key, tip in (
                ("up", N_("Move &up (earlier)"), "PgUp",
                 N_("Move the selected elements one place up the element list: the laser does them earlier")),
                ("down", N_("Move &down (later)"), "PgDown",
                 N_("Move the selected elements one place down the element list: the laser does them later")),
                ("first", N_("To the &start (first)"), "Ctrl+PgUp",
                 N_("Move the selected elements to the top of the element list: the laser does them first")),
                ("last", N_("To the &end (last)"), "Ctrl+PgDown",
                 N_("Move the selected elements to the bottom of the element list: the laser does them last"))):
            act = self._action(_(text), lambda _c=False, h=how: self.reorder_selected(h), key, _(tip))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)    # only while the bed view has focus
            self.preview.addAction(act)
            self.act_order[how] = act
        self.act_text_path = self._action(
            _("Put text on &path"), self.put_text_on_path, None,
            _("Set the selected text along the selected shape (line, curve, circle, ...); the shape stays"))
        self.act_center = self._action(_("&Centre on the bed"), self.center_on_bed, "Ctrl+E",
                                       _("Centre the selected element, or the whole design, on the bed"))
        self.act_snap_objects = self._action(_("Snap to &objects"), self.toggle_snap_objects, "Ctrl+;",
                                             _("Snap to corners, centres, middles and lines of other elements "
                                               "and of the bed, when drawing and moving. Hold Alt to snap "
                                               "nothing for a moment."))
        self.act_snap_objects.setCheckable(True)
        self.act_snap_objects.setChecked(is_true(self.values.get("snap_objects", "1")))
        self.act_snap = self._action(_("&Snap to grid"), self.toggle_snap, "Ctrl+'")
        self.act_snap.setCheckable(True)
        self.act_snap.setChecked(self._grid_mm() > 0)
        self.grid_actions = QActionGroup(self)
        for mm in (1, 2, 5, 10):
            a = self._action(_("%d mm") % mm, lambda _c=False, g=mm: self.set_grid(g))
            a.setCheckable(True)
            a.setChecked(abs(self._grid_size_choice() - mm) < 1e-9)
            self.grid_actions.addAction(a)
        self.act_rot_left = self._action(_("Rotate 90° counter-clockwise"),
                                         lambda: self.rotate_selected(90), "Ctrl+L")
        self.act_rot_right = self._action(_("Rotate 90° clockwise"),
                                          lambda: self.rotate_selected(-90), "Ctrl+R")
        # the same keys as in Inkscape too: Ctrl+[ and Ctrl+] turn by 90°
        self.act_rot_left.setShortcuts([QKeySequence("Ctrl+L"), QKeySequence("Ctrl+[")])
        self.act_rot_right.setShortcuts([QKeySequence("Ctrl+R"), QKeySequence("Ctrl+]")])
        # Group / Ungroup as in Inkscape
        self.act_group = self._action(_("&Group"), self.group_selected, "Ctrl+G",
                                      _("Join the selected elements into a group that is selected and moved "
                                        "as one"))
        self.act_ungroup = self._action(_("U&ngroup"), self.ungroup_selected, "Ctrl+Shift+G",
                                        _("Split the selected group into separate elements"))
        self.act_boolean = {}
        # keys as in Inkscape: Ctrl++ union, Ctrl+- difference, Ctrl+* intersection, Ctrl+^ exclusion
        for code, tip, key in (("union", N_("Union: join the selected shapes into one outline"), "Ctrl++"),
                               ("difference", N_("Difference: cut the other selected shapes out of the first one"),
                                "Ctrl+-"),
                               ("intersection", N_("Intersection: keep only where the selected shapes overlap"),
                                "Ctrl+*"),
                               ("exclusion", N_("Exclusion: keep where the shapes do not overlap"), "Ctrl+^")):
            self.act_boolean[code] = self._action(_(self.BOOLEAN_NAMES[code]),
                                                  lambda _c=False, k=code: self.boolean_selected(k), key, _(tip))
        self.act_join = self._action(_("&Join into a polyline"), self.join_selected, "Ctrl+J",
                                     _("Join into a polyline: the selected lines and open shapes whose ends meet "
                                       "become one path, cut in one go"))
        self.act_offset = self._action(_("&Offset"), lambda: self.set_tool("offset"), None,
                                       _("Offset: a new outline around a shape (or inside it), a set distance "
                                         "away"))
        self.act_offset.setIcon(icons.tabler("box-padding"))
        self.act_trace_image = self._action(_("Trace &picture…"), self.trace_image, None,
                                            _("Trace: the dark areas of the selected picture become paths you can "
                                              "cut, outline, fill or edit node by node"))
        self.act_trace_image.setIcon(icons.tabler("vector-spline"))
        self.act_mirror_h = self._action(_("&Mirror horizontally"), lambda: self.mirror_selected(True), "Ctrl+Shift+H",
                                         _("Flip the selected elements left to right"))
        self.act_mirror_v = self._action(_("Mirror &vertically"), lambda: self.mirror_selected(False), "Ctrl+Shift+V",
                                         _("Flip the selected elements top to bottom"))
        align_names = {"left": N_("Align left"), "hcenter": N_("Align centres horizontally"),
                       "right": N_("Align right"), "top": N_("Align top"),
                       "vcenter": N_("Align centres vertically"), "bottom": N_("Align bottom")}
        self.act_align = {}
        for edge, text in align_names.items():
            self.act_align[edge] = self._action(
                _(text), lambda _c=False, k=edge: self.align_selected(k), None,
                _(text) + " – " + _("several elements: to each other; one element: to the bed"))
        self.act_distribute_h = self._action(_("Distribute horizontally"), lambda: self.distribute_selected(True),
                                             None, _("Spread three or more selected elements evenly from left to right; the leftmost and "
                                               "rightmost stay in place"))
        self.act_distribute_v = self._action(_("Distribute vertically"), lambda: self.distribute_selected(False),
                                             None, _("Spread three or more selected elements evenly from top to bottom; the top and "
                                               "bottom ones stay in place"))
        self.act_place_head = self._action(_("Place design at the &head"), self.place_at_head, "Ctrl+H",
                                           _("Move all elements so the design starts at the laser head"))
        self.act_nest = self._action(_("&Nest on the bed…"), self.nest_selected, "Ctrl+Shift+N",
                                     _("Nest: lay the selected parts out on the laser's bed as tightly as they "
                                       "fit, on more sheets when needed (nothing selected: all of them)"))
        self.act_follow_head = self._action(
            _("Design &follows the head"), self.toggle_follow_head, "Ctrl+Alt+H",
            _("The design moves with the laser head: the arrows, Go to X/Y and Home move both, "
              "as in K40 Whisperer. The corner buttons still only show the corners."))
        self.act_follow_head.setCheckable(True)
        self.act_follow_head.setChecked(is_true(self.values.get("follow_head", "0")))
        self.act_follow_head.setIcon(icons.follow_head_icon())
        self.act_save_gcode = self._action(_("Save &G-code\u2026"), self.save_gcode, "Ctrl+Shift+K",
                                           _("Save G-code for a laser with a GRBL board: the ticked layers "
                                             "with their speed, power and passes"))
        self.act_save_egv = self._action(_("Save &EGV file\u2026"), self.save_egv, "Ctrl+Shift+E",
                                         _("Write the selected operations to an EGV file"))
        self.act_send_egv = self._action(_("Send EGV file to laser\u2026"), self.send_egv_file, None,
                                         _("Send an existing EGV file to the laser"))
        self.act_save_settings = self._action(_("Save settings as default"), self.save_settings)
        self.act_save_project = self._action(_("&Save project"), self.save_project, "Ctrl+S",
                                             _("Save the layout, layers and files in one .kerfly file"))
        self.act_save_project_as = self._action(_("Save project &as\u2026"), self.save_project_as, "Ctrl+Shift+S")
        self.act_goto = self._action(_("&Go to X/Y position"), self.goto_position, "Ctrl+Alt+G")
        self.act_corners = {}
        for key, text, sc in (("UL", N_("Upper left corner"), "Ctrl+7"),
                              ("UR", N_("Upper right corner"), "Ctrl+9"),
                              ("CC", N_("Centre"), "Ctrl+5"), ("LL", N_("Lower left corner"), "Ctrl+1"),
                              ("LR", N_("Lower right corner"), "Ctrl+3")):
            self.act_corners[key] = self._action(_(text), lambda _checked=False, k=key: self.move_to_corner(k), sc)
        self.act_calc_time = self._action(_("Calculate raster time"), self.calculate_raster_time)
        self.act_quit = self._action(_("&Quit"), self.close, "Ctrl+Q")
        self.act_connect = self._action(_("&Initialize laser"), self.connect_laser, "Ctrl+I")
        self.act_release = self._action(_("Release USB"), self.release_laser)
        self.act_home = self._action(_("&Home"), self.home, "Home")
        self.act_unlock = self._action(_("&Unlock rail"), self.unlock)
        self.act_unfreeze = self._action(_("Un&freeze laser"), self.unfreeze)
        # Linux: the udev rule for the laser's USB port, with one click (pkexec asks for the password)
        self.act_usb_access = self._action(_("Allow USB access for the laser…"), self.allow_usb_access,
                                           tip=_("Linux: let this computer's users use the laser's USB port "
                                                 "without root (asks for the administrator password once)"))
        self.act_desktop_entry = self._action(
            _("Add Kerfly to the applications menu…"), self.install_desktop_entry,
            tip=_("Linux AppImage: Kerfly in the menu of your desktop, and .kerfly projects open in Kerfly "
                  "with a double click (only for you, no password)"))
        self.act_fit = self._action(_("&Fit to window"), lambda: self.preview.fit_all(), "Ctrl+0")
        self.act_settings = self._action(_("&Settings\u2026"), self.edit_settings, "Ctrl+,")
        self.act_profiles = self._action(_("&Lasers\u2026"), self.manage_profiles, None,
                                         _("Your lasers and each one's settings (board, bed, homing, power, "
                                           "trace, rotary, USB): use one, add, duplicate, rename, delete, export, "
                                           "import"))
        self.act_materials = self._action(_("&Material library\u2026"), lambda: self.edit_materials())
        self.act_export_materials = self._action(_("&Export material library\u2026"), self.export_materials)
        self.act_import_materials = self._action(_("&Import material library\u2026"), self.import_materials)
        self.act_about = self._action(_("&About Kerfly"), self.about)
        self.act_simulate = self._action(_("&Simulate job\u2026"), self.simulate_job, "Ctrl+Shift+J",
                                         _("Play the laser head's moves in the order the job will run them"))
        self.act_report = self._action(_("Save &diagnostic report…"), self.save_report, None,
                                       _("Save a report with the laser log and settings, to attach to a bug report"))
        self.act_log_folder = self._action(_("Open the &log folder"), self.open_log_folder)
        self.act_check_updates = self._action(
            _("Check for &updates"), lambda: self.check_for_updates(manual=True), None,
            _("Ask GitHub whether a newer Kerfly is out (a bar above the bed links to it)"))
        self.act_shortcuts = self._action(_("&Keyboard shortcuts"), self.show_shortcuts, "Ctrl+F1",
                                          _("All keys and mouse actions in one window"))
        self.act_guide = self._action(_("&User guide"), self.open_guide, "F1",
                                      _("Open the user guide on the Kerfly website"))
        self.act_report_problem = self._action(
            _("Report a &problem on GitHub\u2026"), self.report_problem, None,
            _("Save the diagnostic report and open the bug report form on GitHub"))

        mb = self.menuBar()
        m = mb.addMenu(_("&File"))
        for a in (self.act_new, self.act_open, self.act_add, self.act_reload, None, self.act_save_project,
                  self.act_save_project_as, None, self.act_save_egv, self.act_save_gcode,
                  self.act_send_egv, None, self.act_save_settings, None, self.act_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(_("&Edit"))
        for a in (self.act_undo, self.act_redo, None, self.act_cut, self.act_copy, self.act_paste,
                  self.act_paste_in_place, None, self.act_select_all, self.act_deselect, None,
                  self.act_duplicate, self.act_delete, None,
                  self.act_rot_left, self.act_rot_right, self.act_mirror_h, self.act_mirror_v, None,
                  self.act_group, self.act_ungroup, None, self.act_order["up"], self.act_order["down"],
                  self.act_order["first"], self.act_order["last"], None, self.act_center, self.act_place_head,
                  self.act_nest,
                  self.act_follow_head):
            m.addSeparator() if a is None else m.addAction(a)
        m.addAction(self.act_text_path)
        sub2 = m.addMenu(_("Combine shapes"))
        for a in self.act_boolean.values():
            sub2.addAction(a)
        m.addAction(self.act_join)
        m.addAction(self.act_offset)
        m.addAction(self.act_trace_image)
        sub = m.addMenu(_("Align and distribute"))
        for a in list(self.act_align.values()) + [None, self.act_distribute_h, self.act_distribute_v]:
            sub.addSeparator() if a is None else sub.addAction(a)
        # generators: ready-made designs from a few numbers
        from kerfly.gui.generators import GENERATORS
        self.act_generators = {}
        for key, title, icon, tip, _fields, _make in GENERATORS:
            act = self._action(_(title) + "…", lambda _c=False, k=key: self.open_generator(k), tip=_(tip))
            act.setToolTip("%s\n%s" % (_(title), _(tip)))
            act.setIcon(icons.tabler(icon))
            self.act_generators[key] = act
        m = mb.addMenu(_("&Laser"))
        self.laser_menu = m
        for a in (self.act_connect, self.act_release, None, self.act_home, self.act_unlock,
                  self.act_unfreeze, None, self.act_goto):
            m.addSeparator() if a is None else m.addAction(a)
        sub = m.addMenu(_("Move head to design"))
        for a in self.act_corners.values():
            sub.addAction(a)
        from kerfly.core import udev
        if udev.applies():
            m.addSeparator()
            m.addAction(self.act_usb_access)
        m = mb.addMenu(_("&View"))
        m.addAction(self.act_fit)
        m.addAction(self.act_simulate)
        m.addSeparator()
        m.addAction(self.act_snap)
        m.addAction(self.act_snap_objects)
        sub = m.addMenu(_("Grid size"))
        for a in self.grid_actions.actions():
            sub.addAction(a)
        m = mb.addMenu(_("&Settings"))
        m.addAction(self.act_settings)
        m.addAction(self.act_profiles)
        m.addSeparator()
        for a in (self.act_materials, self.act_export_materials, self.act_import_materials):
            m.addAction(a)
        from kerfly.gui import desktop_entry
        if desktop_entry.applies():
            m.addSeparator()
            m.addAction(self.act_desktop_entry)
            if desktop_entry.installed_for() not in (None, desktop_entry.appimage_path()):
                # added before for another AppImage file (an older version): it now opens this one
                try:
                    desktop_entry.install()
                    diag_log.info("applications menu entry moved to %s", desktop_entry.appimage_path())
                except Exception as e:
                    diag_log.warning("applications menu entry not updated: %s", e)
        # after Laser and Settings, as asked by a user: the daily work comes first
        m = mb.addMenu(_("&Generators"))
        m.setToolTip(_("Ready-made designs from a few numbers: boxes, parts, tests"))
        for section, keys in ((N_("Boxes"), ("finger_box", "hinge_box")),
                              (N_("Parts"), ("gear", "puzzle", "ruler", "qr", "stamp", "round_stamp")),
                              (N_("Tests and calibration"), ("material_test", "kerf_test", "test_card"))):
            m.addSection(_(section))
            for key in keys:
                m.addAction(self.act_generators[key])
        listed = {a for a in m.actions()}
        for act in self.act_generators.values():           # a generator in no section yet: at the end
            if act not in listed:
                m.addAction(act)
        self.generators_menu = m
        m = mb.addMenu(_("&Help"))
        m.addAction(self.act_guide)
        m.addAction(self.act_shortcuts)
        m.addAction(self.act_check_updates)
        m.addSeparator()
        m.addAction(self.act_report_problem)
        m.addAction(self.act_report)
        m.addAction(self.act_log_folder)
        m.addSeparator()
        m.addAction(self.act_about)

        self._build_toolbar()

    def _build_toolbar(self):
        """Toolbar in labelled groups, like the MeerK40t ribbon. Machine control
        (connect, home, start, stop, ...) is in the left panel, not here."""
        self.act_start = self._action(_("Start"), lambda: self.start_job(), "F9",
                                      _("Start the selected operations"))
        self.act_stop = self._action(_("Stop"), self.stop_job, "Esc", _("Pause or stop the running job"))
        self.act_stop.setEnabled(False)
        self.act_trace = self._action(_("Trace boundary"), lambda: self.start_job(trace=True), None,
                                      _("Move around the outline of the design"))
        # one kind of work, as K40 Whisperer's three buttons: all the ticked layers of that kind
        self.act_run_kind = {}
        for kind, text, tip in ((RASTER, N_("Engrave only"), N_("Run only the ticked raster engrave layers")),
                                (ENGRAVE, N_("Outline only"), N_("Run only the ticked outline (vector engrave) "
                                                                  "layers")),
                                (CUT, N_("Cut only"), N_("Run only the ticked cut layers"))):
            act = self._action(_(text), lambda _c=False, k=kind: self.start_job(kinds={k}), None, _(tip))
            act.setToolTip(_(tip))
            pix = QPixmap(14, 14)
            pix.fill(QColor(DEFAULT_LAYER_COLORS[kind]))
            act.setIcon(QIcon(pix))
            self.act_run_kind[kind] = act
        self.laser_menu.addSeparator()
        for a in (self.act_trace, self.act_start) + tuple(self.act_run_kind.values()) + (self.act_stop,):
            self.laser_menu.addAction(a)
        self.act_trace.setIcon(icons.trace_icon())
        self.act_start.setIcon(icons.tabler("player-play", theme.token("start")))
        self.act_stop.setIcon(icons.tabler("player-stop", theme.token("stop")))

        # the ribbon (docs/ui-mockups/Main): groups of big buttons (an icon over a short label) and grids
        # of small icon buttons in two rows, a caption under each group. Machine control (connect, home,
        # start, stop, ...) is in the left panel; Help (report a problem, the report) in its menu only.
        # (title, [(action, icon, label)] big buttons, [(action, icon)] small buttons)
        groups = [
            (C_("toolbar group", "File"), [
                (self.act_new, "file", C_("toolbar", "New")),
                (self.act_open, "folder-open", C_("toolbar", "Open")),
                (self.act_add, "file-plus", C_("toolbar", "Add")),
                (self.act_save_project, "device-floppy", C_("toolbar", "Save")),
            ], [
                (self.act_reload, "refresh"),
                (self.act_save_egv, "file-export"),
                (self.act_save_gcode, "file-gcode"),
            ]),
            (C_("toolbar group", "Edit"), [
                (self.act_undo, "arrow-back-up", C_("toolbar", "Undo")),
                (self.act_redo, "arrow-forward-up", C_("toolbar", "Redo")),
            ], [
                (self.act_cut, "scissors"),
                (self.act_copy, "copy"),
                (self.act_paste, "clipboard"),
                (self.act_paste_in_place, "clipboard-plus"),
                (self.act_duplicate, "copy-plus"),
                (self.act_delete, "trash"),
                (self.act_select_all, "select-all"),
                (self.act_group, "squares-selected"),
                (self.act_ungroup, "squares"),
            ]),
            (C_("toolbar group", "Arrange"), [], [
                (self.act_align["left"], "layout-align-left"),
                (self.act_align["hcenter"], "layout-align-center"),
                (self.act_align["right"], "layout-align-right"),
                (self.act_distribute_h, "layout-distribute-vertical"),
                (self.act_rot_left, "rotate-2"),
                (self.act_mirror_h, "flip-horizontal"),
                (self.act_center, "focus-centered"),
                (self.act_nest, "nest"),
                (self.act_align["top"], "layout-align-top"),
                (self.act_align["vcenter"], "layout-align-middle"),
                (self.act_align["bottom"], "layout-align-bottom"),
                (self.act_distribute_v, "layout-distribute-horizontal"),
                (self.act_rot_right, "rotate-clockwise-2"),
                (self.act_mirror_v, "flip-vertical"),
                (self.act_place_head, "current-location"),
            ]),
            (C_("toolbar group", "Shapes"), [], [
                (self.act_boolean["union"], "layers-union"),
                (self.act_boolean["difference"], "layers-subtract"),
                (self.act_join, "join-polyline"),
                (self.act_boolean["intersection"], "layers-intersect-2"),
                (self.act_boolean["exclusion"], "layers-difference"),
            ]),
            (C_("toolbar group", "View"), [
                (self.act_fit, "zoom-scan", C_("toolbar", "Fit")),
                (self.act_simulate, "movie", C_("toolbar", "Simulate")),
                (self.act_snap, "grid-dots", C_("toolbar", "Grid")),
            ], []),
            (C_("toolbar group", "Tools"), [
                (self.generators_menu, "box", C_("toolbar", "Generators")),
                (self.act_materials, "book", C_("toolbar", "Materials")),
                (self.act_settings, "settings", C_("toolbar", "Settings")),
            ], []),
        ]
        tb = QToolBar(_("Main toolbar"))
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        self._ribbon_groups = []
        for i, (title, big, small) in enumerate(groups):
            if i:
                tb.addWidget(ribbon_separator())
            group = QWidget()
            v = QVBoxLayout(group)
            v.setContentsMargins(theme.SPACE_S, theme.SPACE_S, theme.SPACE_S, 0)
            v.setSpacing(0)
            row = QHBoxLayout()
            row.setSpacing(2)
            for what, icon, short in big:
                button = QToolButton()
                if isinstance(what, QMenu):              # a list under the button (Generators)
                    button.setMenu(what)
                    button.setPopupMode(QToolButton.InstantPopup)
                    button.setIcon(icons.tabler(icon))
                    button.setText(short)
                    button.setToolTip(what.toolTip())
                    button.setObjectName("generators_button")
                    self.generators_button = button
                else:
                    what.setIcon(icons.tabler(icon))
                    what.setIconText(short)
                    if not what.toolTip() or what.toolTip() == what.iconText():
                        what.setToolTip(what.text().replace("&", ""))
                    button.setDefaultAction(what)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setIconSize(QSize(theme.ICON_LARGE, theme.ICON_LARGE))
                button.setAutoRaise(True)
                button.setFixedHeight(theme.RIBBON_BUTTON)
                row.addWidget(button, 0, Qt.AlignTop)
            if small:
                grid = QGridLayout()
                grid.setSpacing(0)
                per_row = (len(small) + 1) // 2           # two rows of small buttons, as tall as a big one
                for n, (action, icon) in enumerate(small):
                    action.setIcon(icons.tabler(icon) if isinstance(icon, str) else icon)
                    grid.addWidget(widgets.icon_button(action=action), n // per_row, n % per_row)
                row.addLayout(grid)
                if i == 1:                                  # Edit: Edit nodes joins it (_build_tool_strip)
                    self._edit_grid = (grid, len(small) // per_row, len(small) % per_row)
            v.addLayout(row)
            v.addStretch(1)
            caption = QLabel(title)
            caption.setObjectName("ribbon_caption")
            caption.setAlignment(Qt.AlignHCenter)
            v.addWidget(caption)
            self._ribbon_groups.append(group)
            tb.addWidget(group)
        self.addToolBar(tb)

    def _build_tool_strip(self):
        """Vertical strip of drawing tools on the right of the bed view (like LightBurn's)."""
        strip = QToolBar(_("Drawing tools"))
        strip.setObjectName("tool_strip")
        strip.setMovable(False)
        strip.setOrientation(Qt.Vertical)
        strip.setIconSize(QSize(24, 24))
        strip.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        # three groups: selecting, drawing, and the extra operations on shapes (None: separator)
        tools = [("select", "pointer", N_("Select and move"), "S"),
                 ("nodes", "vector", N_("Edit nodes"), "N"),
                 None,
                 ("rectangle", "square", N_("Rectangle"), "R"),
                 ("ellipse", "circle", N_("Ellipse"), "E"),
                 ("polygon", "hexagon", N_("Polygon"), "P"),
                 ("line", "line", N_("Line"), "L"),
                 ("polyline", "polygon", N_("Polyline"), "Shift+L"),
                 ("pen", "vector-bezier-2", N_("Pen (curves)"), "B"),
                 ("freehand", "scribble", N_("Freehand"), "F"),
                 ("text", "typography", N_("Text"), "T"),
                 None,
                 ("textpath", icons.text_on_path_icon(), N_("Text on a path"), "Shift+T"),
                 ("fill", "bucket-droplet", N_("Fill with a pattern"), "Shift+F"),
                 ("hinge", icons.hinge_icon(), N_("Living hinge"), "Shift+H"),
                 ("offset", "box-padding", N_("Offset"), "Shift+O"),
                 ("crop", "picture-cut", N_("Cut out of a picture"), "Shift+C"),
                 ("measure", "ruler-measure", N_("Measure"), "M")]
        for entry in tools:
            if entry is None:
                strip.addSeparator()
                continue
            key, icon, name, shortcut = entry
            act = QAction(icons.tabler(icon) if isinstance(icon, str) else icon, _(name), self)
            act.setCheckable(True)
            act.setShortcut(QKeySequence(shortcut))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)    # only while the bed view has focus
            act.setToolTip("%s (%s)" % (_(name), shortcut))
            act.triggered.connect(lambda _c=False, k=key: self.set_tool(k))
            self.tool_group.addAction(act)
            self.preview.addAction(act)
            if key != "nodes":                     # Edit nodes is on the ribbon, in the Edit group
                strip.addAction(act)
            self.tool_actions[key] = act
        self.tool_actions["select"].setChecked(True)
        grid, row, col = self._edit_grid
        grid.addWidget(widgets.icon_button(action=self.tool_actions["nodes"]), row, col)
        # Trace image (a command, not a tool) with the tools that work on a picture or a shape
        strip.insertAction(self.tool_actions["measure"], self.act_trace_image)
        strip.insertSeparator(self.tool_actions["measure"])
        self.addToolBar(Qt.RightToolBarArea, strip)
        # Inkscape's H and V mirror the selection (only with the bed view in focus, like the tool letters)
        self.mirror_keys = []
        for key, horizontal in (("H", True), ("V", False)):
            act = QAction(self)
            act.setShortcut(QKeySequence(key))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(lambda _c=False, h=horizontal: self.mirror_selected(h))
            self.preview.addAction(act)
            self.mirror_keys.append(act)

    def set_tool(self, tool):
        self.tool_actions[tool].setChecked(True)
        if tool == "nodes":
            self.status(_("Edit nodes: click a shape, drag its nodes and the round curve handles (Ctrl: one "
                          "handle alone). Shift+click selects more nodes. Double-click a side to add a node, a node "
                          "to remove it. Buttons above, or keys I D L C O S Z B."))
        if tool == "measure":
            self.status(_("Measure: drag from one point to another. Points snap to corners, centres and lines, "
                          "as when drawing (hold Alt for free points)."))
        if tool == "freehand":
            self.status(_("Freehand: draw with the mouse button held. End near the start to close the shape. The "
                          "line is smoothed into curves you can edit with Edit nodes."))
        if tool == "pen":
            self.status(_("Pen: click for a corner, press and drag for a smooth curve. Click the first point to "
                          "close the shape; double-click or Enter finishes an open path. Backspace removes the "
                          "last node, Shift keeps 45\u00b0 angles, Esc cancels."))
        if tool == "hinge":
            self.status(_("Living hinge: choose the cuts above, then click a closed shape to cut them into it. "
                          "Selected shapes get the hinge you choose. The border stays solid."))
        if tool == "textpath":
            self.status(_("Text on a path: click a line, curve or shape to put the selected text on it (no text "
                          "selected: type a new one above first). Drag the text afterwards to slide it along the "
                          "line."))
        if tool == "offset":
            self.status(_("Offset: set the distance above, then click a closed shape to draw a new outline around "
                          "it (negative: inside it). Shapes selected before: Offset selected."))
        if tool == "fill":
            self.status(_("Fill: choose a pattern above, then click a closed shape (cut or outline) to fill it. "
                          "Selected shapes get the pattern you choose. The outline stays on its layer; the "
                          "pattern is engraved."))
        if tool == "crop":
            self.status(_("Cut out of a picture: drag a rectangle or an ellipse (options bar) over a picture; the "
                          "piece inside stays, the rest goes. Undo brings it back."))
        if tool == "polyline":
            self.status(_("Polyline: click the corners. Click the first point to close the shape; double-click or "
                          "press Enter to finish an open line. Backspace removes the last corner, Shift keeps "
                          "45\u00b0 angles, Esc cancels."))
        self.preview.set_tool(tool)
        if tool != "select":
            self.preview.setFocus()
        self._update_tool_options()

    def _update_tool_options(self, force=False):
        if self.preview.tool == "nodes":                 # the node buttons alone (docs/ui-mockups/OptionBars)
            e = self.selected
            self._options_target, self._options_element = ("nodes", e) if e is not None else (None, None)
            self.tool_options.show_hint()
            self.tool_options.add_node_actions()
            ed = self.preview.node_editor
            self.tool_options.set_node_selection(len(ed.selected) if ed.path is not None else 0)
            return
        if self.preview.tool in ("fill", "hinge"):
            tool = self.preview.tool
            spec, key = self._pattern_tool_spec(tool)
            if force or getattr(self, "_options_target", None) != tool \
                    or getattr(self, "_options_element", None) != key:
                self._options_target, self._options_element = tool, key
                self._tool_shown = spec.copy()
                if tool == "fill":
                    self.tool_options.show_fill_tool(spec)
                else:
                    self.tool_options.show_hinge_tool(spec)
            return
        if self.preview.tool == "crop":
            if force or getattr(self, "_options_target", None) != "crop":
                self._options_target, self._options_element = "crop", None
                self.tool_options.show_crop_tool(self.crop_defaults)
            return
        if self.preview.tool == "offset":
            if force or getattr(self, "_options_target", None) != "offset":
                self._options_target, self._options_element = "offset", None
                self.tool_options.show_offset_tool(self.offset_defaults)
            return
        if self.preview.tool == "textpath":
            e = self.selected
            if e is not None and e.shape is not None and e.shape.kind == "text":
                # a selected text is the one the tool puts on the clicked shape: show it
                if force or getattr(self, "_options_target", None) != "selected" \
                        or getattr(self, "_options_element", None) is not e:
                    self._options_target, self._options_element = "selected", e
                    self.tool_options.show_spec(e.shape, e.name)
            elif force or getattr(self, "_options_target", None) != "textpath":
                self._options_target, self._options_element = "textpath", None
                title = NEW_KIND_TITLES["textpath"]
                self.tool_options.show_spec(self.shape_defaults["textpath"], _(title))
            return
        e = self.selected
        if e is not None and e.shape is not None:
            if not force and getattr(self, "_options_target", None) == "selected" \
                    and getattr(self, "_options_element", None) is e:
                return                   # already shown; rebuilding would interrupt typing
            self._options_target, self._options_element = "selected", e
            self.tool_options.show_spec(e.shape, e.name)
        elif e is not None and e.design.raster.image is not None and self.preview.tool == "select":
            if force or getattr(self, "_options_target", None) != "picture" \
                    or getattr(self, "_options_element", None) is not e:
                self._options_target, self._options_element = "picture", e
                self.tool_options.show_picture([self.act_trace_image])
        elif self.preview.tool in self.shape_defaults:
            self._options_target, self._options_element = self.preview.tool, None
            self.tool_options.show_spec(self.shape_defaults[self.preview.tool],
                                        _(NEW_KIND_TITLES[self.preview.tool]))
        else:
            self._options_target, self._options_element = None, None
            self.tool_options.show_hint()

    FILL_ATTRS = ("fill_pattern", "fill_spacing", "fill_angle", "fill_margin", "fill_outline")
    HINGE_ATTRS = ("hinge_pattern", "hinge_cut", "hinge_gap", "hinge_spacing", "hinge_angle", "hinge_margin",
                   "hinge_band", "hinge_band_offset")

    def _pattern_tool_spec(self, tool):
        """What the bar of the Fill / Living hinge tool shows: with shapes selected,
        what they have now ("No pattern" for a shape without a pattern, not the
        pattern a click would give); otherwise the pattern a click gives.
        Returns (spec, key of the selection)."""
        if tool == "fill":
            defaults, fits, attrs = self.fill_defaults, self._fillable, self.FILL_ATTRS
        else:
            defaults, fits, attrs = self.hinge_defaults, self._hingeable, self.HINGE_ATTRS
        chosen = [e for e in self._selection() if fits(e)]
        if not chosen:
            return defaults, ()
        e = self.selected if self.selected in chosen else chosen[0]
        spec = defaults.copy()
        if getattr(e.shape, attrs[0]):
            for attr in attrs:
                setattr(spec, attr, getattr(e.shape, attr))
        else:
            setattr(spec, attrs[0], "")
        return spec, tuple(sorted(id(c) for c in chosen))

    def _pattern_tool_changed(self, tool, spec):
        """A field of the Fill / Living hinge tool bar changed: selected shapes take it,
        and a click on another shape gives it."""
        if tool == "fill":
            fits, give, attr = self._fillable, self._fill_element, "fill_pattern"
        else:
            fits, give, attr = self._hingeable, self._hinge_element, "hinge_pattern"
        shown = getattr(self, "_tool_shown", None)
        if not getattr(spec, attr) and shown is not None and not getattr(shown, attr):
            # a number changed while the bar says "none": nothing to give the selected shapes,
            # and a click still gives the pattern chosen last
            keep = spec.copy()
            setattr(keep, attr, getattr(self.fill_defaults if tool == "fill" else self.hinge_defaults, attr))
            if tool == "fill":
                self.fill_defaults = keep
            else:
                self.hinge_defaults = keep
            self._tool_shown = spec.copy()
            return
        if tool == "fill":
            self.fill_defaults = spec
        else:
            self.hinge_defaults = spec
        self._tool_shown = spec.copy()
        chosen = [e for e in self._selection() if fits(e)]
        if chosen:                                   # selected shapes take the chosen pattern
            self._checkpoint()
            for e in chosen:
                give(e, checkpoint=False)
            self._keep_selection(chosen)

    def _tool_options_changed(self, spec):
        target = getattr(self, "_options_target", None)
        if target in ("fill", "hinge"):
            self._pattern_tool_changed(target, spec)
            return
        if target == "selected" and self.selected is not None and self.selected.shape is not None:
            before = self.selected.shape.operation
            had_fill = bool(self.selected.shape.fill_pattern)
            had_path = bool(self.selected.shape.text_path)
            had_hinge = bool(self.selected.shape.hinge_pattern)
            was_closed = self.selected.shape.closed      # a single-line font: open lines, no Fill / Bridges
            if had_path and spec.text_path:
                # the bar's copy of the path is from before the last change (every change moves
                # the path's frame): the element's own path is the right one
                spec.text_path = [tuple(p) for p in self.selected.shape.text_path]
            self._apply_shape(self.selected, spec)
            self.tool_options.spec = self.selected.shape.copy()      # the bar edits what is on the bed now
            if had_fill != bool(spec.fill_pattern) or had_path != bool(spec.text_path) \
                    or had_hinge != bool(spec.hinge_pattern) or was_closed != spec.closed:    # sections appear / go
                QTimer.singleShot(0, self, lambda: self._update_tool_options(force=True))
        elif target in self.shape_defaults:
            before = self.shape_defaults[target].operation
            if self.shape_defaults[target].closed != spec.closed:
                QTimer.singleShot(0, self, lambda: self._update_tool_options(force=True))
            self.shape_defaults[target] = spec
        else:
            return
        if before != spec.operation:              # e.g. the Fill or Bridges section appears
            QTimer.singleShot(0, self, lambda: self._update_tool_options(force=True))

    # ---- Fill tool ----------------------------------------------------------
    @staticmethod
    def _fillable(e):
        return e.shape is not None and e.shape.closed and e.shape.operation in ("cut", "engrave", "hatch")

    def _fill_element(self, e, checkpoint=True):
        """Give the Fill tool's pattern to a drawn closed shape (a hatch becomes
        an outline with the pattern)."""
        spec = e.shape.copy()
        d = self.fill_defaults
        spec.fill_pattern, spec.fill_spacing, spec.fill_angle = d.fill_pattern, d.fill_spacing, d.fill_angle
        spec.fill_margin, spec.fill_outline = d.fill_margin, d.fill_outline
        if spec.operation == "hatch":
            spec.operation = "engrave"
        self._apply_shape(e, spec, checkpoint=checkpoint)

    def _shape_picked(self, tool, point):
        if tool == "textpath":
            self._text_path_clicked(point)
        elif tool == "hinge":
            self._hinge_clicked(point)
        elif tool == "offset":
            self._offset_clicked(point)
        else:
            self._fill_clicked(point)

    def _bed_point(self, point):
        """Scene mm (x right, y down on screen) -> bed inches (y up)."""
        bed_w, _bed_h = config.bed_size_inches(self.values)
        x = point.x() / 25.4
        if self.job_settings().home_upper_right:
            x = bed_w - x
        return x, -point.y() / 25.4

    def _shape_lines(self, e):
        """The drawn element's polylines on the bed (inches), with their design frame."""
        from kerfly.core.shapes import _bounds_mm, outlines
        polys = [p for p in outlines(e.shape) if len(p) >= 2]
        if not polys:
            return []
        xmin, _xmax, ymin, ymax = _bounds_mm(polys)
        h_in = (ymax - ymin) / 25.4
        f = e.transform()
        return [[f((px - xmin) / 25.4, h_in - (py - ymin) / 25.4) for px, py in p] for p in polys]

    def _line_at(self, point, tolerance_mm=None):
        """The drawn element (not a text) whose line is nearest to the point, if it
        is close enough (a few pixels on screen), or one whose closed outline holds it."""
        from kerfly.core.shapes import element_contains
        x, y = self._bed_point(point)
        if tolerance_mm is None:
            scale = abs(self.preview.transform().m11()) or 1.0          # pixels per mm
            tolerance_mm = max(1.0, 8.0 / scale)
        tol = tolerance_mm / 25.4
        best, best_d = None, None
        for e in self.elements:
            if not e.visible or e.shape is None or e.shape.kind == "text":
                continue
            b = e.bounds
            if not (b[0] - tol <= x <= b[1] + tol and b[2] - tol <= y <= b[3] + tol):
                continue
            d = None
            for line in self._shape_lines(e):
                for (x1, y1), (x2, y2) in zip(line, line[1:]):
                    ex, ey = x2 - x1, y2 - y1
                    ll = ex * ex + ey * ey
                    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * ex + (y - y1) * ey) / ll))
                    dd = math.hypot(x1 + t * ex - x, y1 + t * ey - y)
                    d = dd if d is None else min(d, dd)
            if d is not None and d > tol and element_contains(e, x, y):
                d = tol * 0.999                                          # inside a closed shape: it counts
            if d is not None and d <= tol and (best_d is None or d < best_d):
                best, best_d = e, d
        return best

    def _text_path_clicked(self, point):
        """Text on a path tool: put the selected text on the clicked shape, or a new text
        (from the options bar) when no text is selected."""
        guide = self._line_at(point)
        if guide is None:
            self.status(_("Click a line, curve or shape to put the text on. Opened files must be ungrouped first "
                          "(Edit → Ungroup)."), error=True)
            return
        chosen = self.selected
        if chosen is not None and chosen.shape is not None and chosen.shape.kind == "text":
            self._checkpoint()                          # move the selected text onto the shape (no copy)
            if not self._place_on_path(chosen, guide):
                self._undo.pop()
                return
            self.set_tool("select")
            self.preview.select_element(chosen)
            self.selected = chosen
            self._update_tool_options(force=True)
            self.status(_("Text put on the path. Drag it to slide it along the line; the bar above changes the "
                          "text, the spacing, the distance from the line and the side."))
            return
        spec = self.shape_defaults["textpath"].copy()
        if not (spec.text or "").strip():
            self.status(_("Type the text in the bar above first."), error=True)
            return
        update_text_spec(spec)
        name = KIND_NAMES["text"]
        text = Element(build_design(spec), name=_(name), shape=spec)
        self._checkpoint()
        self.elements.append(text)
        self._place_on_path(text, guide)
        self.set_tool("select")
        self.preview.select_element(text)
        self.selected = text
        self._update_tool_options(force=True)
        self.status(_("Text put on the path. Drag it to slide it along the line; the bar above changes the text, "
                      "the spacing, the distance from the line and the side."))

    def _element_inside(self, point):
        """The element whose area holds the clicked point (scene mm): inside its closed
        outline first, else inside its frame; the smallest one when several do. None if none."""
        from kerfly.core.shapes import element_contains
        try:
            x, y = self._bed_point(point)
        except ValueError as ex:
            self.status(str(ex), error=True)
            return None
        hits = [e for e in self.elements if e.visible and e.bounds[0] <= x <= e.bounds[1]
                and e.bounds[2] <= y <= e.bounds[3]]
        if not hits:
            return None
        inside = [e for e in hits if element_contains(e, x, y)]
        return min(inside or hits, key=lambda h: (h.bounds[1] - h.bounds[0]) * (h.bounds[3] - h.bounds[2]))

    def _keep_selection(self, chosen):
        """Select these elements again after they were rebuilt (the bed view redraws
        them and kept only one selected: the next change reached only that one)."""
        current = self.selected if self.selected in chosen else chosen[-1]
        self.preview.select_element(list(chosen))
        self.selected = current

    # ---- Living hinge tool -------------------------------------------------------
    @staticmethod
    def _hingeable(e):
        return e.shape is not None and e.shape.kind != "text" and e.shape.closed \
            and e.shape.operation in ("cut", "engrave")

    def _hinge_element(self, e, checkpoint=True):
        spec = e.shape.copy()
        for attr in self.HINGE_ATTRS:
            setattr(spec, attr, getattr(self.hinge_defaults, attr))
        self._apply_shape(e, spec, checkpoint=checkpoint)

    def _hinge_clicked(self, point):
        """The Living hinge tool was clicked at a point of the bed view (scene mm)."""
        e = self._element_inside(point)
        if e is None:
            self.status(_("Click inside a closed shape to cut a hinge into it."), error=True)
            return
        if e.shape is None:
            self.status(_("Only drawn shapes can get a hinge. Ungroup an opened file first (Edit → Ungroup)."),
                        error=True)
            return
        if not self._hingeable(e):
            self.status(_("A living hinge needs a closed shape (not a text) on a cut or outline layer."), error=True)
            return
        self._hinge_element(e)
        self.preview.select_element(e)
        self.selected = e
        # the bar shows what the shape has now (it may have been selected already: no new selection)
        self._update_tool_options(force=True)
        if self.hinge_defaults.hinge_pattern:
            self.status(_("Hinge cut into the shape. Click another shape, or change the cuts above."))
        else:
            self.status(_("Hinge removed."))

    def _fill_clicked(self, point):
        """The Fill tool was clicked at a point of the bed view (scene mm)."""
        e = self._element_inside(point)
        if e is None:
            self.status(_("Click inside a shape to fill it."), error=True)
            return
        if e.shape is None:
            self.status(_("Only drawn shapes can be filled. Ungroup an opened file first (Edit → Ungroup) to "
                          "fill its shapes."), error=True)
            return
        if not self._fillable(e):
            self.status(_("Only closed shapes on a cut or outline layer can be filled with a pattern."), error=True)
            return
        self._fill_element(e)
        self.preview.select_element(e)
        self.selected = e
        # the bar shows what the shape has now (it may have been selected already: no new selection)
        self._update_tool_options(force=True)
        if self.fill_defaults.fill_pattern:
            self.status(_("Filled. Click another shape, or change the pattern above."))
        else:
            self.status(_("Pattern removed."))

    def _apply_shape(self, element, spec, checkpoint=True):
        """Rebuild a drawn element from a changed spec, keeping its top-left corner
        (text on a path: keeping its path in place)."""
        if checkpoint:
            self._checkpoint()
        anchor = spec.text_path[0] if spec.kind == "text" and spec.text_path else None
        old_w = element.size[0]
        if spec.kind == "text":
            update_text_spec(spec)
            if spec.single_line and spec.operation in ("fill", "hatch"):
                spec.operation = "engrave"      # a single-line font has no area to fill: its lines are engraved
        x, y = element.x, element.y
        element.shape = spec
        element.design = build_design(spec)
        element.x, element.y = x, y
        if anchor is not None and spec.text_path and element.is_identity:
            # the outlines start at (0, 0) again: move the element so the path stays where it was
            dx, dy = anchor[0] - spec.text_path[0][0], anchor[1] - spec.text_path[0][1]     # mm, screen
            if self.job_settings().home_upper_right:
                element.x = x + old_w - element.size[0] - dx / 25.4
            else:
                element.x = x + dx / 25.4
            element.y = y - dy / 25.4
        self._keep_on_bed(element)
        self._layout_changed()

    def put_text_on_path(self):
        """Edit → Put text on path: the selected text along the selected shape."""
        chosen = self._selection()
        texts = [e for e in chosen if e.shape is not None and e.shape.kind == "text"]
        guides = [e for e in chosen if e.shape is not None and e.shape.kind != "text"]
        if len(texts) != 1 or not guides:
            self.status(_("Select one text and one shape (line, curve, circle, ...) to put the text on, then "
                          "choose Put text on path again (Ctrl+click selects both)."), error=True)
            return
        self._checkpoint()
        if not self._place_on_path(texts[0], guides[0]):
            self._undo.pop()
            return
        self.preview.select_element(texts[0])
        self.selected = texts[0]
        self.status(_("Text put on the path. The path stays: delete it if it should not be cut. Move the text "
                      "along the path or to the other side in the bar above."))

    def _place_on_path(self, text, guide):
        """Set the text element along the longest line of the guide element (no undo step)."""
        from kerfly.gui.text_shapes import prepare_path, text_length
        lines = self._shape_lines(guide)
        if not lines:
            self.status(_("That shape has no line to put the text on."), error=True)
            return False
        bed_w, _bed_h = config.bed_size_inches(self.values)
        ur = self.job_settings().home_upper_right
        longest = max(lines, key=lambda p: sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(p, p[1:])))
        screen = [((bed_w - bx) * 25.4 if ur else bx * 25.4, -by * 25.4) for bx, by in longest]
        closed = guide.shape.closed and len(longest) > 3
        spec = text.shape.copy()
        spec.text_path, spec.text_path_offset = prepare_path(screen, closed, text_length(spec))
        spec.text_path_flip = False
        update_text_spec(spec)
        # the outlines start at (0, 0): the path was only moved (maybe reversed, or a ring started
        # elsewhere), so its smallest x and y show where the element's top-left corner is
        mx = min(x for x, _ in screen) - min(x for x, _ in spec.text_path)
        my = min(y for _, y in screen) - min(y for _, y in spec.text_path)
        text.rotation, text.scale_x, text.scale_y = 0.0, 1.0, 1.0
        text.shape = spec
        text.design = build_design(spec)
        w_in = text.size[0]
        text.x = bed_w - mx / 25.4 - w_in if ur else mx / 25.4
        text.y = -my / 25.4
        self._keep_on_bed(text)
        self._compiled = None
        self._layout_changed()
        return True

    def _preview_drawn(self, tool, start, end, shift):
        """A shape was drawn in the bed view (scene mm, y down)."""
        if tool == "cancel":
            self.set_tool("select")
            return
        if tool == "crop":
            self.crop_picture(start, end)
            return
        spec = self.shape_defaults[tool].copy()
        dx, dy = end.x() - start.x(), end.y() - start.y()
        clicked = abs(dx) < 0.5 and abs(dy) < 0.5
        if tool == "text":
            update_text_spec(spec)
            left, top = start.x(), start.y()
        elif tool == "line":
            if clicked:
                dx, dy = 20.0, 0.0
            if shift:                                    # 0 / 45 / 90 degree steps
                import math
                angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(dx, dy)
                dx, dy = length * math.cos(angle), length * math.sin(angle)
            spec.width, spec.height = dx, dy
            left, top = min(start.x(), start.x() + dx), min(start.y(), start.y() + dy)
        else:
            if clicked:
                dx, dy = 20.0, 20.0
            if shift:
                side = max(abs(dx), abs(dy))
                dx, dy = (side if dx >= 0 else -side), (side if dy >= 0 else -side)
            spec.width, spec.height = abs(dx), abs(dy)
            left, top = min(start.x(), start.x() + dx), min(start.y(), start.y() + dy)
        self._add_drawn_element(spec, tool, left, top)

    def _preview_measured(self, dx, dy):
        import math
        k, unit = (1.0, "mm") if self.values.get("units", "mm") == "mm" else (1 / 25.4, "in")
        self.status(_("Distance %(d).2f %(u)s: width %(w).2f %(u)s, height %(h).2f %(u)s, angle %(a).1f\u00b0")
                    % {"d": math.hypot(dx, dy) * k, "w": abs(dx) * k, "h": abs(dy) * k, "u": unit,
                       "a": math.degrees(math.atan2(-dy, dx))})

    def _preview_pen_drawn(self, subpaths):
        """A path was drawn with the pen (scene mm)."""
        tool = self.preview.tool
        e = Element(Design(), name=_("Freehand") if tool == "freehand" else _("Path"))
        if not self._fit_path(e, subpaths, self.shape_defaults["pen"]):
            self.status(_("Nothing to draw."), error=True)
            return
        self._checkpoint()
        self._keep_on_bed(e)
        self.elements.append(e)
        self.selected = e
        self._compiled = None
        self.set_tool("select")
        self._layout_changed()

    def _preview_polyline_drawn(self, points, closed):
        """A polyline was drawn (scene mm, y down)."""
        xs, ys = [p.x() for p in points], [p.y() for p in points]
        left, top = min(xs), min(ys)
        spec = self.shape_defaults["polyline"].copy()
        spec.points = [(p.x() - left, p.y() - top) for p in points]
        spec.closed_path = bool(closed)
        spec.width, spec.height = max(xs) - left, max(ys) - top
        if not spec.closed and spec.operation in ("fill", "hatch"):
            spec.operation = "cut" if spec.operation == "fill" else "engrave"                         # an open line has no area to fill
        self._add_drawn_element(spec, "polyline", left, top)

    # ---- node editing -----------------------------------------------------
    NODE_KINDS = ("polyline", "line", "rectangle", "ellipse", "polygon")

    def _node_points(self, element):
        """The shape's path in item coordinates (mm, y down, top-left at 0, 0),
        or None when it cannot be node-edited."""
        from kerfly.core import curves
        spec = element.shape
        from kerfly.core.explode import has_vectors
        if self.preview.tool == "nodes" and spec is None and element.design is not None \
                and has_vectors(element.design):
            self.status(_("This is an opened file: click Ungroup first, then every line is its own shape you "
                          "can move or double-click to edit."), error=True)
            return None
        if spec is None or spec.kind not in self.NODE_KINDS + ("path",):
            if self.preview.tool == "nodes":
                self.status(_("This element has no lines to edit. For a filled text, change its operation to "
                              "Cut or Engrave outline first; a picture has no nodes."), error=True)
            return None
        if spec.kind == "path":
            return curves.copy_path(spec.subpaths)
        if spec.kind == "polyline":
            return curves.from_polylines([spec.points], [spec.closed_path])
        if spec.kind == "ellipse":                       # a real ellipse: four Bezier quarters
            rx, ry = abs(spec.width) / 2.0, abs(spec.height) / 2.0
            segs = curves.arc_segments(rx, ry, 0, 0, 360, rx=rx, ry=ry)
            return curves.join_segments(segs, 1e-9)
        poly = outlines(spec)[0]
        closed = spec.closed
        if closed and len(poly) > 1 and poly[0] == poly[-1]:
            poly = poly[:-1]
        return curves.from_polylines([poly], [closed])

    def _fit_path(self, e, scene_subpaths, base_spec):
        """Make element e a path (lines and curves) through scene_subpaths (scene
        mm), keeping its rotation, scale and mirror. False when nothing is left."""
        import math
        from PySide6.QtGui import QTransform
        from kerfly.core import curves
        lin = QTransform().rotate(-e.rotation).scale(e.scale_x, e.scale_y)
        inv, ok = lin.inverted()
        if not ok or not scene_subpaths:
            return False

        def to_local(x, y):
            return inv.map(x, y)
        local = []
        for sp in scene_subpaths:
            nodes = []
            for n in sp["nodes"]:
                x, y = to_local(n[0], n[1])
                hin = to_local(n[2], n[3]) if n[2] is not None else None
                hout = to_local(n[4], n[5]) if n[4] is not None else None
                nodes.append(curves.node(x, y, hin, hout))
            local.append({"closed": bool(sp.get("closed")), "nodes": nodes})
        local, (dx, dy) = curves.normalized(local)
        spec = base_spec.copy()
        spec.kind = "path"
        spec.subpaths = local
        spec.points, spec.closed_path = [], False
        x0, x1, y0, y1 = curves.bounds(local)
        spec.width, spec.height = x1, y1
        if not spec.closed and spec.operation in ("fill", "hatch"):
            spec.operation = "cut" if spec.operation == "fill" else "engrave"
        design = build_design(spec)
        xmin, xmax, ymin, ymax = design.bounds
        if xmax - xmin <= 0 and ymax - ymin <= 0:
            return False
        e.shape = spec
        e.design = design
        # place it so that the first node lands on its scene position
        first = local[0]["nodes"][0]
        w0, h0 = (xmax - xmin) * 25.4, (ymax - ymin) * 25.4
        vx, vy = lin.map(first[0] - w0 / 2.0, first[1] - h0 / 2.0)
        sx, sy = scene_subpaths[0]["nodes"][0][0], scene_subpaths[0]["nodes"][0][1]
        cx, cy = sx - vx, sy - vy
        if self.preview.home_ur:
            cx = self.preview.bed_w_mm - cx
        e.set_centre(cx / 25.4, -cy / 25.4)
        return math.isfinite(e.x) and math.isfinite(e.y)

    def _nodes_changed(self, element, scene_subpaths, _unused=True):
        """The node tool changed the shape (scene mm). It becomes a path of lines
        and curves; rotation, scale and mirror of the element are kept."""
        if element not in self.elements or element.shape is None:
            return
        snapshot = self._snapshot()
        old = (element.shape, element.design, element.placement())
        if not self._fit_path(element, scene_subpaths, element.shape):
            element.shape, element.design = old[0], old[1]
            element.set_placement(old[2])
            return
        self._set_dirty(True)
        self._undo.append(snapshot)
        del self._undo[:-100]
        self._redo.clear()
        self._layer_cache.clear()
        self._layout_changed()
        self.preview.select_element(element)
        self._update_tool_options(force=True)        # now a path: no more "sides" or "radius"

    # ---- boolean operations on shapes ------------------------------------
    BOOLEAN_NAMES = {"union": N_("Union"), "difference": N_("Difference"),
                     "intersection": N_("Intersection"), "exclusion": N_("Exclusion")}

    def boolean_selected(self, op):
        """Combine the closed outlines of the selected elements into one shape:
        union, difference (the first minus the others), intersection or
        exclusion (where an odd number of them overlap)."""
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPainterPath
        from kerfly.core.curves import from_polylines
        chosen = self._selection()
        items = {id(i.element): i for i in self.preview._items}
        parts = []
        for e in chosen:
            item = items.get(id(e))
            if item is None:
                continue
            t = item.sceneTransform()
            path = QPainterPath()
            path.setFillRule(Qt.OddEvenFill)
            for poly in item.local_polys:
                if len(poly) >= 4 and abs(poly[0][0] - poly[-1][0]) < 1e-6 and abs(poly[0][1] - poly[-1][1]) < 1e-6:
                    pts = [QPointF(*t.map(x, y)) for x, y in poly]
                    path.moveTo(pts[0])
                    for q in pts[1:]:
                        path.lineTo(q)
                    path.closeSubpath()
            if not path.isEmpty():
                parts.append((e, path))
        if len(parts) < 2 or self.worker is not None:
            self.status(_("Select two or more shapes with closed outlines."), error=True)
            return
        result = parts[0][1]
        for _e, path in parts[1:]:
            if op == "union":
                result = result.united(path)
            elif op == "difference":
                result = result.subtracted(path)
            elif op == "intersection":
                result = result.intersected(path)
            else:
                result = result.united(path).subtracted(result.intersected(path))
        polys = []
        for poly in result.simplified().toSubpathPolygons():
            pts = [(p.x(), p.y()) for p in poly]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 3:
                polys.append(pts)
        if not polys:
            self.status(_("Nothing is left of the shapes after this operation."), error=True)
            return
        first = parts[0][0]
        op_kind = first.shape.operation if first.shape is not None else "cut"
        new = Element(Design(), name=_(self.BOOLEAN_NAMES[op]), visible=first.visible)
        if not self._fit_path(new, from_polylines(polys, [True] * len(polys)), ShapeSpec(kind="path", operation=op_kind)):
            self.status(_("Nothing is left of the shapes after this operation."), error=True)
            return
        new.layers = dict(first.layers)
        self._checkpoint()
        index = self.elements.index(first)
        for e, _p in parts:
            self.elements.remove(e)
        self.elements.insert(min(index, len(self.elements)), new)
        self.selected = new
        self._compiled = None
        self._layer_cache.clear()
        self._layout_changed()

    def nest_selected(self):
        """Nest on the bed: the selected parts (nothing selected: all; a group as one part) laid out on the
        laser's bed by their rectangles or by their real outlines (in each other's gaps and holes, sparrow, in a
        thread with a progress window), turned where that fits better; what does not fit goes on next sheets,
        each a group named Sheet N, sheets 2 and on unticked (a sheet is always the bed). The sheets of an
        earlier nesting are undone first, so their parts are laid out again. One undo step."""
        import re
        from kerfly.core.groups import top, without, wrap
        from kerfly.core.nesting import nest
        from kerfly.gui.nest_dialog import NestDialog
        if self.worker is not None:
            return
        chosen = self._selection() or list(self.elements)
        if not chosen:
            self.status(_("Nothing to nest: open or draw something first."), error=True)
            return
        try:
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        sheet_name = _("Sheet %d")
        is_sheet = re.compile("^" + re.escape(sheet_name).replace("%d", r"\d+") + "$")
        def outer(e):                                # the group it is nested with (not an earlier sheet)
            g = e.group
            if g and is_sheet.match(self.group_names.get(top(g), "")):
                g = without(g, top(g))
            return top(g) or id(e)
        dlg = NestDialog(self.nest_defaults, (bed_w * 25.4, bed_h * 25.4), len({outer(e) for e in chosen}), self)
        if not dlg.exec():
            return
        self.nest_defaults = dlg.values()
        self._checkpoint()
        for e in chosen:                             # the sheets of an earlier nesting: laid out again
            if e.group and is_sheet.match(self.group_names.get(top(e.group), "")):
                e.group = without(e.group, top(e.group))
                e.visible = True
        d = self.nest_defaults
        if d.get("method") == "outlines":
            from kerfly.core.nesting import apply_outline_plan
            from kerfly.gui.nest_dialog import plan_with_progress
            try:
                planned = plan_with_progress(self, chosen, bed_w, bed_h, d["gap"], d["turn"], d.get("seconds", 10))
            except RuntimeError as e:
                planned = str(e)
            if not isinstance(planned, tuple):       # cancelled or failed: nothing changed
                self._restore(self._undo.pop())
                if planned:
                    self.status(_("Nesting by outlines failed: %s") % planned, error=True)
                else:
                    self.status(_("Nesting cancelled: nothing moved."))
                return
            placed, sheets = apply_outline_plan(planned[0], planned[1], bed_h)
        else:
            placed, sheets = nest(chosen, bed_w, bed_h, d["gap"], d["turn"])
        if sheets > 1:
            for n in range(1, sheets + 1):
                gid = self._new_group_id()
                self.group_names[gid] = sheet_name % n
                for els, sheet in placed:
                    if sheet == n:
                        for e in els:
                            e.group = wrap(e.group, "", gid)
                            if n > 1:
                                e.visible = False
        self.preview.scope = ""
        self._arranged(chosen)
        if sheets > 1:
            self.status(_("Nested %(n)d parts on %(s)d sheets; in the element list each sheet is a group, sheets 2 "
                          "and on unticked: cut sheet 1, then untick it and tick the next one.")
                        % {"n": len(placed), "s": sheets})
        else:
            self.status(_("Nested %d parts on the bed.") % len(placed))

    JOIN_GAP_MM = 0.05          # ends closer than this are joined (as LightBurn's Auto-Join)

    def join_selected(self):
        """Join into a polyline: the open lines of the selected shapes whose ends meet (closer than
        JOIN_GAP_MM) become one path each, cut in one go (no stop at every piece on a GRBL or CNC machine);
        a chain whose ends meet is closed. Closed outlines stay as they are. One undo step."""
        from kerfly.core import curves
        if self.worker is not None:
            return
        items = {id(i.element): i for i in self.preview._items}
        sources = []                                 # (element, its closed subpaths, its open ones), scene mm
        for e in self._selection():
            item = items.get(id(e))
            if item is None or e.shape is None:
                continue
            local = self._node_points(e)
            if not local:
                continue
            t = item.sceneTransform()

            def m(x, y, t=t):
                return t.map(x, y)
            scene = []
            for sp in local:
                nodes = []
                for n in sp["nodes"]:
                    x, y = m(n[0], n[1])
                    nodes.append(curves.node(x, y, m(n[2], n[3]) if n[2] is not None else None,
                                             m(n[4], n[5]) if n[4] is not None else None))
                scene.append({"closed": bool(sp.get("closed")), "nodes": nodes})
            opens = [sp for sp in scene if not sp["closed"] and len(sp["nodes"]) > 1]
            if opens:
                sources.append((e, [sp for sp in scene if sp["closed"]], opens))
        if not sources:
            self.status(_("Select the lines to join: open shapes (lines, polylines, paths). An opened file: "
                          "Ungroup it first."), error=True)
            return
        joined = curves.join_segments([seg for _e, _c, opens in sources for sp in opens
                                       for seg in curves.segments_of(sp)], self.JOIN_GAP_MM)

        def ends(sp):                                # what tells a line apart: its pieces and its two ends
            segs = curves.segments_of(sp)
            return len(segs), frozenset((round(p[0], 3), round(p[1], 3)) for p in (segs[0][0], segs[-1][3]))
        same = {ends(sp) for sp in joined if not sp["closed"]}       # lines that came out as they went in
        # a shape none of whose lines met another one (nor closed) stays as it is, and so do its lines
        untouched = [src for src in sources if all(ends(sp) in same for sp in src[2])]
        kept_lines = {ends(sp) for _e, _c, opens in untouched for sp in opens}
        sources = [src for src in sources if src not in untouched]
        joined = [sp for sp in joined if sp["closed"] or ends(sp) not in kept_lines]
        pieces = sum(len(o) for _e, _c, o in sources)
        closed_now = sum(1 for sp in joined if sp["closed"])
        if not sources or not joined:
            self.status(_("No ends of the selected lines meet (closer than %s mm): nothing to join.")
                        % self.JOIN_GAP_MM, error=True)
            return
        first = sources[0][0]
        group = first.group if all(e.group == first.group for e, _c, _o in sources) else ""
        made = []
        for sp in joined:
            new = Element(Design(), name=_("Path"), visible=first.visible, group=group)
            if self._fit_path(new, [sp], ShapeSpec(kind="path", operation=first.shape.operation)):
                new.layers = dict(first.layers)
                made.append(new)
        kept = []                                    # the closed outlines of a source with open lines too
        for e, closed, _o in sources:
            if closed:
                rest = Element(Design(), name=e.name, visible=e.visible, group=e.group)
                if self._fit_path(rest, closed, e.shape.copy()):
                    rest.layers = dict(e.layers)
                    kept.append(rest)
        if not made:
            self.status(_("No ends of the selected lines meet (closer than %s mm): nothing to join.")
                        % self.JOIN_GAP_MM, error=True)
            return
        self._checkpoint()
        index = min(self.elements.index(e) for e, _c, _o in sources)
        for e, _c, _o in sources:
            self.elements.remove(e)
        self.elements[index:index] = made + kept
        self.selected = made[0] if len(made) == 1 else None
        self._compiled = None
        self._layer_cache.clear()
        self._layout_changed()
        self.preview.select_element(made)
        self.status(_("Joined %(pieces)d lines into %(paths)d path(s), %(closed)d of them closed.")
                    % {"pieces": pieces, "paths": len(made), "closed": closed_now})

    def _offset_values_changed(self, values):
        self.offset_defaults = dict(values)

    def _offset_clicked(self, point):
        """The Offset tool was clicked at a point of the bed view (scene mm)."""
        e = self._element_inside(point)
        if e is None:
            self.status(_("Click inside a closed shape to offset it."), error=True)
            return
        self._offset_elements([e])

    def offset_selected(self):
        """The Offset tool's button: offset the shapes selected now."""
        self._offset_elements(self._selection())

    def _offset_elements(self, chosen):
        """A new outline around each shape (or inside it), the Offset tool's
        distance away: the closed outlines are joined even-odd, so holes move
        the other way. The shapes are kept or replaced (one undo step)."""
        from kerfly.core import offset
        from kerfly.core.curves import from_polylines
        if self.worker is not None:
            return
        if not offset.available():
            self.status(_("Offset needs the pyclipper library, which is missing."), error=True)
            return
        v = self.offset_defaults
        distance = float(v["offset_distance"])
        if abs(distance) < 1e-9:
            self.status(_("Set a distance other than 0 first."), error=True)
            return
        items = {id(i.element): i for i in self.preview._items}
        parts = []
        for e in chosen:
            item = items.get(id(e))
            if item is None:
                continue
            t = item.sceneTransform()
            polys = [[t.map(x, y) for x, y in poly] for poly in item.local_polys
                     if len(poly) >= 4 and abs(poly[0][0] - poly[-1][0]) < 1e-6
                     and abs(poly[0][1] - poly[-1][1]) < 1e-6]
            if polys:
                parts.append((e, polys))
        if not parts:
            self.status(_("Select one or more shapes with closed outlines."), error=True)
            return
        made = []
        for e, polys in parts:
            rings = [r[:-1] for r in offset.offset_polygons(polys, distance, v["offset_join"])]
            if not rings:
                continue
            kind = e.shape.operation if e.shape is not None else "cut"
            new = Element(Design(), name="%s: %s" % (_("Offset"), e.name) if e.name else _("Offset"),
                          visible=e.visible)
            if self._fit_path(new, from_polylines(rings, [True] * len(rings)), ShapeSpec(kind="path", operation=kind)):
                new.layers = dict(e.layers)
                made.append((e, new))
        if not made:
            self.status(_("Nothing is left of the shapes after this operation."), error=True)
            return
        self._checkpoint()
        for e, new in made:
            index = self.elements.index(e)
            if v["offset_keep"]:
                self.elements.insert(index + 1, new)
            else:
                self.elements[index] = new
        news = [n for _e, n in made]
        self.selected = news[0] if len(news) == 1 else None
        self._compiled = None
        self._layer_cache.clear()
        self._arranged(news)
        if len(news) == 1:
            self.preview.select_element(news[0])
        self.status(_("Offset done. Click another shape, or change the distance above."))

    def _node_selection_changed(self, count):
        self.tool_options.set_node_selection(count)
        if self.preview.tool == "nodes" and self.preview.node_editor.path is None:
            self.status(_("Click a shape to edit its nodes."))
        elif self.preview.tool == "nodes":
            if count == 0:
                self.status(_("Click a node (small square) to select it; Shift+click for more. Then use the "
                              "buttons above."))
            else:
                self.status(_("Selected nodes: %d. Drag them, or use the buttons above.") % count)

    def _edit_nodes_of(self, element):
        """Double-click on an element: edit its nodes (an opened file: ungroup it first)."""
        from kerfly.core.explode import has_vectors
        if element not in self.elements or self.worker is not None:
            return
        if element.shape is None and has_vectors(element.design):
            self.status(_("This is an opened file: click Ungroup first, then every line is its own shape you "
                          "can move or double-click to edit."), error=True)
            return
        self.set_tool("nodes")
        self.preview.select_element(element)

    def _split_pictures(self, elements, checkpoint=True):
        """Split pictures into their separate parts (areas that do not touch),
        each a picture element of its own in the same place. Returns the new
        elements (none when a picture has only one part)."""
        import tempfile
        from kerfly.core.explode import raster_pieces
        from kerfly.gui.preview import element_transform
        made = []
        folder = None
        for e in elements:
            image, dpi = e.design.raster.image, e.design.input_dpi or 1000.0
            pieces = raster_pieces(image, dpi)
            if len(pieces) < 2:
                continue
            if checkpoint and not made:
                self._checkpoint()
            folder = folder or tempfile.mkdtemp(prefix="kerfly_pieces_")
            t = element_transform(e, self.preview.home_ur, self.preview.bed_w_mm)
            index = self.elements.index(e)
            new = []
            for n, (box, piece) in enumerate(pieces, 1):
                # stored as a PNG so projects can keep the piece like any opened picture
                path = os.path.join(folder, "%s_%d.png" % (os.path.splitext(os.path.basename(e.name))[0] or "part", n))
                piece.save(path, dpi=(dpi, dpi))
                d = Design()
                d.input_dpi = dpi
                d.raster.set_image(piece)
                d.bounds = (0.0, piece.width / dpi, 0.0, piece.height / dpi)
                part = Element(d, name="%s %d" % (e.name, n), source_file=path, load_options={"dpi": dpi},
                               rotation=e.rotation, scale_x=e.scale_x, scale_y=e.scale_y, visible=e.visible,
                               layers=dict(e.layers), origin=self._element_path(e))
                cx_mm, cy_mm = t.map((box[0] + box[2]) / 2.0 / dpi * 25.4, (box[1] + box[3]) / 2.0 / dpi * 25.4)
                if self.preview.home_ur:
                    cx_mm = self.preview.bed_w_mm - cx_mm
                part.set_centre(cx_mm / 25.4, -cy_mm / 25.4)
                new.append(part)
            self.elements[index:index + 1] = new
            made += new
        if made:
            self._compiled = None
            self._layer_cache.clear()
        return made

    # ---- break apart ------------------------------------------------------
    def _curve_paths(self, e):
        """The lines of an opened SVG / DXF with their real curves, in design
        inches (y up), one subpath each: [(kind, [subpath], True)]. None when the
        file cannot be read this way or does not match what the laser gets."""
        from kerfly.core import curves, loaders
        from kerfly.core.explode import vector_loops
        if e.shape is not None or not e.source_file or not os.path.isfile(e.source_file):
            return None
        ext = os.path.splitext(e.source_file)[1].lower()
        try:
            if ext == ".svg":
                ppi = float((e.load_options.get("svg_scale") or [96.0])[0] or 96.0)
                found = curves.svg_segments(e.source_file, ppi=ppi)
                top = e.design.bounds[3]
                found = {k: [tuple(None if p is None else (p[0], top - p[1]) for p in s) for s in v]
                         for k, v in found.items()}
            elif ext == ".dxf":
                import dxf as _dxf
                reader = _dxf.DXF_CLASS()
                with open(e.source_file) as fd:
                    reader.GET_DXF_DATA(fd, lin_tol=.0005, get_units=True, units=None)
                units = e.load_options.get("dxf_units") or reader.units
                scale = loaders.DXF_UNIT_SCALE.get(units)
                if scale is None:
                    return None
                found = curves.dxf_segments(e.source_file, scale)
            else:
                return None
        except Exception as ex:
            diag_log.warning("break apart: curves not read from %s: %r", e.source_file, ex)
            return None
        out = []
        for kind, attr in (("engrave", "vector_engrave"), ("cut", "vector_cut")):
            subs = curves.join_segments(found.get(kind, []), tol=1e-5)
            k40 = getattr(e.design, attr).ecoords
            flat = [p for poly in curves.flatten(subs, tol=0.0002) for p in poly]
            if bool(flat) != bool(k40):
                return None
            if flat:
                ours = (min(p[0] for p in flat), max(p[0] for p in flat), min(p[1] for p in flat), max(p[1] for p in flat))
                theirs = (min(r[0] for r in k40), max(r[0] for r in k40), min(r[1] for r in k40), max(r[1] for r in k40))
                if max(abs(a - b) for a, b in zip(ours, theirs)) > 0.004:     # inches: not the same drawing
                    diag_log.info("break apart: curves of %s do not match (%s / %s), using lines",
                                  e.source_file, ours, theirs)
                    return None
            out += [(kind, [sp], True) for sp in subs]
        return out

    def break_apart_selected(self, grouped=True):
        """Every vector path of the selected elements becomes its own polyline
        (cut or outline engrave as before), grouped so they stay together. An
        image part stays as it was."""
        from PySide6.QtCore import QPointF
        from kerfly.core.curves import from_polylines, node
        from kerfly.core.explode import has_vectors, raster_only, vector_loops
        from kerfly.gui.preview import element_transform
        chosen = [e for e in self._selection() if e.design is not None and has_vectors(e.design)
                  and not (e.shape is not None and e.shape.kind in self.NODE_KINDS)]
        if not chosen or self.worker is not None:
            self.status(_("Select an opened file or a text with lines to break it apart."), error=True)
            return
        loops = [(e, self._curve_paths(e) or [(k, from_polylines([pts], [c]), True)
                                             for k, pts, c in vector_loops(e.design)]) for e in chosen]
        total = sum(len(l) for _e, l in loops)
        if total > 300 and widgets.ask(
                self, _("Break apart"),
                _("This makes %d separate shapes, which can make Kerfly slow. Continue?") % total,
                QMessageBox.Yes | QMessageBox.No, names={QMessageBox.Yes: _("Break apart")}) != QMessageBox.Yes:
            return
        self._checkpoint()
        made = []
        for e, paths in loops:
            xmin, xmax, ymin, ymax = e.design.bounds
            t = element_transform(e, self.preview.home_ur, self.preview.bed_w_mm)
            gid = (e.group or self._new_group_id()) if grouped else ""
            index = self.elements.index(e)
            parts = []
            for n, (kind, sub, _design_units) in enumerate(paths, 1):
                def to_scene(x, y):                       # design inches (y up) -> scene mm
                    return t.map((x - xmin) * 25.4, (ymax - y) * 25.4)
                scene_path = []
                for sp in sub:
                    nodes = []
                    for nd in sp["nodes"]:
                        px, py = to_scene(nd[0], nd[1])
                        hin = to_scene(nd[2], nd[3]) if nd[2] is not None else None
                        hout = to_scene(nd[4], nd[5]) if nd[4] is not None else None
                        nodes.append(node(px, py, hin, hout))
                    scene_path.append({"closed": sp["closed"], "nodes": nodes})
                part = Element(e.design, name="%s %d" % (e.name, n), rotation=e.rotation,
                               scale_x=e.scale_x, scale_y=e.scale_y, visible=e.visible, group=gid,
                               origin=self._element_path(e))
                base = ShapeSpec(kind="path", operation=kind)
                if self._fit_path(part, scene_path, base):
                    if e.layers.get(kind):
                        part.layers[kind] = e.layers[kind]
                    parts.append(part)
            if e.design.raster.image is not None:          # the picture part stays
                e.design = raster_only(e.design)
                e.load_options["raster_only"] = True
                e.group = gid
                index += 1
            else:
                self.elements.remove(e)
            self.elements[index:index] = parts
            made += parts
        self.selected = None
        self._compiled = None
        self._layer_cache.clear()
        self._arranged(made)
        if grouped:
            self.status(_("Broken apart into %d shapes (grouped; use Ungroup to separate them).") % len(made))
        else:
            self.status(_("Ungrouped into %d shapes: click one to move it, double-click it to edit its "
                          "nodes.") % len(made))

    def _add_drawn_element(self, spec, tool, left, top):
        if spec.kind == "path" and spec.subpaths:
            # the node editor draws the nodes from (0, 0) of the outline: a path must start there
            from kerfly.core import curves
            spec.subpaths = curves.normalized(spec.subpaths)[0]
        design = build_design(spec)
        xmin, xmax, ymin, ymax = design.bounds
        if xmax - xmin <= 0 and ymax - ymin <= 0:
            self.status(_("Nothing to draw."), error=True)
            return
        self._checkpoint()
        element = Element(design, name=_(KIND_NAMES[tool]), shape=spec)
        bed_w, bed_h = config.bed_size_inches(self.values)
        width_in = xmax - xmin
        if self.job_settings().home_upper_right:
            element.x = bed_w - left / 25.4 - width_in
        else:
            element.x = left / 25.4
        element.y = -top / 25.4
        self._keep_on_bed(element)
        self.elements.append(element)
        self.selected = element
        self._compiled = None
        self.set_tool("select")
        self._layout_changed()

    def _update_lock_icon(self, locked):
        self.sel_lock.setIcon(icons.tabler("link" if locked else "link-off"))
        self.sel_lock.setToolTip(_("Proportions are kept") if locked
                                 else _("Proportions are not kept: width and height change separately"))

    def _spin(self, key, kind, lo, hi, decimals=1):
        if kind == "int":
            w = QSpinBox()
            w.setRange(int(lo), int(hi))
            w.setValue(int(float(self.values.get(key) or 1)))
            w.valueChanged.connect(lambda v: self._set_value(key, str(v)))
        else:
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setDecimals(decimals)
            if kind == "power":
                w.setSuffix(" %")
                w.setValue(float(self.values.get(key) or 0) * 100.0)
                w.valueChanged.connect(lambda v: self._set_value(key, _num_text(v / 100.0)))
            else:
                w.setValue(float(self.values.get(key) or 0))
                w.valueChanged.connect(lambda v: self._set_value(key, _num_text(v)))
                self._unit_widgets.append((w, kind, key, 1.0))
        # compact columns in the operations table
        samples = {"int": 100, "power": 100, "speed": 9999.9}
        if kind in samples:
            fit_spin(w, samples[kind])
        return w

    def _panel_header(self, title, *extra):
        """A section's header in the left panel: its bold title, then other widgets (HEIGHT_OPTION_ROW)."""
        box = QWidget()
        box.setFixedHeight(theme.HEIGHT_OPTION_ROW)
        h = QHBoxLayout(box)
        h.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_M, 0)
        h.setSpacing(theme.SPACE_M)
        h.addWidget(widgets.section_title(title))
        for w in extra:
            h.addWidget(w)
        if not extra:
            h.addStretch(1)
        return box

    def _build_panel(self):
        # the left panel (docs/ui-mockups/Main and LaserTab): flat, two tabs, Design (elements, layers) and
        # Laser (the device, moving the head); the job's buttons in a bar at its bottom, under both tabs
        panel = QWidget()
        panel.setObjectName("left_panel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("panel_tabs")
        self.tabs.setDocumentMode(True)
        design_page, laser_page = QWidget(), QWidget()
        design_layout = QVBoxLayout(design_page)
        laser_layout = QVBoxLayout(laser_page)
        for lay in (design_layout, laser_layout):
            lay.setContentsMargins(0, 0, 0, theme.SPACE_L)
            lay.setSpacing(0)
        self.tabs.addTab(design_page, _("Design"))
        self.tabs.addTab(laser_page, _("Laser"))
        layout.addWidget(self.tabs, 1)

        # --- Elements: the count and size of the design, the job order buttons, the list
        self.design_label = widgets.hint(_("No design loaded"), wrap=False)
        self.design_label.setMinimumWidth(0)
        order_buttons = []
        for how, icon in (("first", "arrow-bar-to-up"), ("up", "arrow-up"), ("down", "arrow-down"),
                          ("last", "arrow-bar-to-down")):
            act = self.act_order[how]
            act.setIcon(icons.tabler(icon))
            b = widgets.icon_button(action=act)
            b.setToolTip("%s (%s)\n%s" % (act.text().replace("&", ""), act.shortcut().toString(),
                                          act.statusTip()))
            order_buttons.append(b)
        self.element_header = self._panel_header(_("Elements"), self.design_label, *order_buttons)
        design_layout.addWidget(self.element_header)
        self.design_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.design_label.parentWidget().layout().setStretchFactor(self.design_label, 1)
        from kerfly.gui.element_tree import ElementTree
        self.element_list = ElementTree()
        # fills the free height of the Design tab
        self.element_list.setMinimumHeight(self.element_list.fontMetrics().lineSpacing() * 4 + 8)
        self.element_list.setToolTip(_("Untick an element to leave it out of the job"))
        self.element_list.itemChanged.connect(self._element_item_changed)
        self.element_list.setSelectionMode(QAbstractItemView.ExtendedSelection)   # Ctrl / Shift: several
        self.element_list.setIconSize(QSize(3 * self.element_list.fontMetrics().height(),
                                             self.element_list.fontMetrics().height()))
        self.element_list.itemSelectionChanged.connect(self._list_selection_changed)
        self.element_list.setMouseTracking(True)       # the path of the row under the pointer, below
        self.element_list.itemEntered.connect(
            lambda item, _column=0: self._show_path(self.elements[self.element_list.row(item)]
                                                    if 0 <= self.element_list.row(item) < len(self.elements)
                                                    else None))
        self.element_list.viewport().installEventFilter(self)
        self.element_list_box = QWidget()
        lb = QHBoxLayout(self.element_list_box)
        lb.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_L, 0)
        lb.addWidget(self.element_list, 1)
        design_layout.addWidget(self.element_list_box, 1)
        # nothing on the bed yet: what to do, in the list's place (instead of an empty panel)
        self.empty_state = QWidget()
        ev = QVBoxLayout(self.empty_state)
        ev.setContentsMargins(theme.PAD_DIALOG, 2 * theme.PAD_DIALOG, theme.PAD_DIALOG, theme.PAD_DIALOG)
        ev.setSpacing(theme.SPACE_M)
        picture = widgets.icon_pixmap_label("file-plus", size=2 * theme.ICON_LARGE)
        picture.setAlignment(Qt.AlignHCenter)
        ev.addWidget(picture)
        title = widgets.section_title(_("No elements yet"))
        title.setAlignment(Qt.AlignHCenter)
        ev.addWidget(title)
        hint = widgets.hint(_("Open a design file, draw a shape with the tools on the right, or make one with a "
                              "generator."))
        hint.setAlignment(Qt.AlignHCenter)
        ev.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_M)
        row.addStretch(1)
        open_button = QToolButton()
        open_button.setDefaultAction(self.act_open)
        generators_button = QToolButton()
        generators_button.setMenu(self.generators_menu)
        generators_button.setPopupMode(QToolButton.InstantPopup)
        generators_button.setIcon(icons.tabler("box"))
        generators_button.setText(C_("toolbar", "Generators"))
        generators_button.setToolTip(self.generators_menu.toolTip())
        for b in (open_button, generators_button):
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setIconSize(QSize(theme.ICON, theme.ICON))
            b.setFixedHeight(theme.HEIGHT_BUTTON)
            row.addWidget(b)
        row.addStretch(1)
        ev.addLayout(row)
        ev.addStretch(1)
        design_layout.addWidget(self.empty_state, 1)

        # --- the options bar's first row, always the same: the selection's position and size, rotation, layer
        self.selection_box = QWidget()
        sb = QHBoxLayout(self.selection_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(theme.SPACE_M)
        sb.addWidget(option_title(_("Selection")))
        sb.addWidget(widgets.separator())
        self.sel_fields = {}
        for key, icon, label, tip in (("x", None, N_("X"), N_("Distance right from home")),
                                      ("y", None, N_("Y"), N_("Distance down from home")),
                                      ("w", "arrows-horizontal", None, N_("Width")),
                                      ("h", "line-height", None, N_("Height"))):
            spin = QDoubleSpinBox()
            spin.setRange(-10000.0 if key in "xy" else 0.0, 10000.0)     # 0: the height of a level line
            spin.setDecimals(2)
            fit_spin(spin, -9999.99)
            spin.setKeyboardTracking(False)          # apply on Enter / focus out, not per digit
            spin.setToolTip(_(tip))
            spin.valueChanged.connect(lambda _v, k=key: self._selection_field_changed(k))
            caption = _(label) if label else (C_("option bar", "W") if key == "w" else C_("option bar", "H"))
            sb.addWidget(option_field(icon, caption, spin))
            self.sel_fields[key] = spin
        self.sel_lock = widgets.icon_button(checkable=True)
        self.sel_lock.setChecked(True)
        self.sel_lock.toggled.connect(self._update_lock_icon)
        self._update_lock_icon(True)
        sb.addWidget(self.sel_lock)
        sb.addWidget(widgets.separator())
        self.sel_rotation = QDoubleSpinBox()
        self.sel_rotation.setRange(-360.0, 360.0)
        self.sel_rotation.setDecimals(1)
        self.sel_rotation.setSuffix("\u00b0")
        fit_spin(self.sel_rotation, -359.9)
        self.sel_rotation.setKeyboardTracking(False)
        self.sel_rotation.setToolTip(_("Rotation, counter-clockwise. You can also drag the round handle "
                                       "above the element (hold Shift for 15\u00b0 steps)."))
        self.sel_rotation.valueChanged.connect(lambda _v: self._selection_field_changed("rotation"))
        sb.addWidget(option_field("angle", _("Rotation"), self.sel_rotation))
        for icon, tip, angle in (("rotate-2", _("Rotate 90\u00b0 counter-clockwise"), 90),
                                 ("rotate-clockwise-2", _("Rotate 90\u00b0 clockwise"), -90)):
            b = widgets.icon_button(icon, tip)
            b.clicked.connect(lambda _c=False, a=angle: self.rotate_selected(a))
            sb.addWidget(b)
        # the layer of each part of the selected element (one list per part, in a row)
        self.layer_assign_box = QWidget()
        la = QGridLayout(self.layer_assign_box)
        la.setContentsMargins(0, 0, 0, 0)
        la.setHorizontalSpacing(theme.SPACE_S)
        self.layer_assign_section = QWidget()
        ls = QHBoxLayout(self.layer_assign_section)
        ls.setContentsMargins(0, 0, 0, 0)
        ls.setSpacing(theme.SPACE_M)
        ls.addWidget(widgets.separator())
        ls.addWidget(option_field("stack-2", _("Layer"), self.layer_assign_box,
                                  _("The layer of each part of the selected element")))
        self.layer_assign_section.hide()
        sb.addWidget(self.layer_assign_section)
        sb.addStretch(1)
        self.selection_row.layout().addWidget(self.selection_box, 1)

        # --- Laser tab, Device: the laser in use (one at a time: its profile sets the board, bed, power, ...),
        # whether it is connected, the machine's buttons
        laser_layout.addWidget(self._panel_header(_("Device")))
        profile_row = QHBoxLayout()
        profile_row.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_L, 0)
        profile_row.setSpacing(theme.SPACE_M)
        self.profile_box = QComboBox()
        self.profile_box.setToolTip(_("The laser in use: choosing another one puts its settings (board, bed, "
                                      "power, rotary, ...) into the window"))
        self.profile_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.profile_box.setMinimumContentsLength(14)
        self.profile_box.activated.connect(lambda _i: self.switch_profile(self.profile_box.currentText()))
        profile_row.addWidget(widgets.icon_pixmap_label("laser", _("The laser in use")))
        profile_row.addWidget(self.profile_box, 1)
        # the cog: the action's own icon (a button's icon would give way to the action's empty one, showing
        # its text cut to "L…y" instead)
        self.act_profiles.setIcon(icons.tabler("settings"))
        manage = widgets.icon_button(action=self.act_profiles)
        manage.setToolTip(_("Your lasers and their settings (board, bed, homing, power, trace, rotary, USB)"))
        self.btn_profiles = manage
        profile_row.addWidget(manage)
        laser_layout.addLayout(profile_row)
        self._refresh_profile_box()
        state = QHBoxLayout()
        state.setContentsMargins(theme.SPACE_L, theme.SPACE_M, theme.SPACE_L, 0)
        state.setSpacing(theme.SPACE_M)
        self.laser_dot = widgets.status_dot()
        self.laser_label = widgets.hint("", wrap=False)
        state.addWidget(self.laser_dot)
        state.addWidget(self.laser_label, 1)
        laser_layout.addLayout(state)
        # the machine's buttons: square, icons only (their names and keys in the tooltips), in a column left
        # of the jog pad (they are added there, below)
        def machine_button(icon, tip, slot):
            b = QPushButton(icons.tabler(icon), "")
            b.setIconSize(QSize(theme.ICON_LARGE, theme.ICON_LARGE))
            b.setFixedSize(theme.HEIGHT_ACTION, theme.HEIGHT_ACTION)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b
        self.btn_connect = machine_button("plug-connected", _("Connect to the laser") + " (Ctrl+I)",
                                          self.connect_laser)
        self.btn_home = machine_button("home", _("Home: move the head to the home corner"), self.home)
        self.btn_unlock = machine_button("lock-open", _("Unlock rail: release the motors so the head can be moved "
                                                        "by hand"), self.unlock)
        # design follows the head: a toggle (highlighted when on), its meaning in the tooltip
        self.btn_follow_head = QToolButton()
        self.btn_follow_head.setDefaultAction(self.act_follow_head)
        self.btn_follow_head.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn_follow_head.setIconSize(QSize(theme.ICON_LARGE, theme.ICON_LARGE))
        self.btn_follow_head.setFixedSize(theme.HEIGHT_ACTION, theme.HEIGHT_ACTION)
        self.btn_follow_head.setAutoRaise(False)          # a button like the others beside it (pressed when on)
        self.act_follow_head.setToolTip("%s (Ctrl+Alt+H)\n%s" % (_("Design follows the head"),
                                                                    self.act_follow_head.statusTip()))
        machine = QVBoxLayout()
        machine.setSpacing(theme.SPACE_S)
        for b in (self.btn_connect, self.btn_home, self.btn_unlock, self.btn_follow_head):
            machine.addWidget(b)
        laser_layout.addSpacing(theme.SPACE_L)

        # --- Head movement: where the head is, the jog pad (arrows move the head by a step; corners and
        # centre move it to that point of the design, the design stays where it is), the step, go to X / Y
        self.head_label = widgets.hint("", wrap=False)
        self.head_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header = self._panel_header(_("Head movement"), self.head_label)
        header.layout().setStretchFactor(self.head_label, 1)
        laser_layout.addWidget(widgets.separator(vertical=False))
        laser_layout.addWidget(header)
        grid = QGridLayout()
        grid.setSpacing(theme.SPACE_S)
        arrows = {(0, 1): ("up", 0, 1, "Ctrl+Up", N_("Move the laser head up by one step")),
                  (-1, 0): ("left", 1, 0, "Ctrl+Left", N_("Move the laser head left by one step")),
                  (1, 0): ("right", 1, 2, "Ctrl+Right", N_("Move the laser head right by one step")),
                  (0, -1): ("down", 2, 1, "Ctrl+Down", N_("Move the laser head down by one step"))}
        for d, (name, r, c, sc, tip) in arrows.items():
            b = QPushButton()
            b.setIcon(icons.arrow_icon(name))
            b.setIconSize(QSize(JOG_ICON, JOG_ICON))
            b.setFixedSize(JOG_BUTTON, JOG_BUTTON)
            b.setToolTip("%s (%s)" % (_(tip), sc))
            b.clicked.connect(lambda _checked=False, d=d: self.jog(*d))
            grid.addWidget(b, r, c)
            act = QAction(self)
            act.setShortcut(QKeySequence(sc))
            act.triggered.connect(lambda _checked=False, d=d: self.jog(*d))
            self.addAction(act)
        self.corner_buttons = []
        corners = (("UL", 0, 0, N_("Move the head to the upper left corner of the design"), "Ctrl+7"),
                   ("UR", 0, 2, N_("Move the head to the upper right corner of the design"), "Ctrl+9"),
                   ("CC", 1, 1, N_("Move the head to the centre of the design"), "Ctrl+5"),
                   ("LL", 2, 0, N_("Move the head to the lower left corner of the design"), "Ctrl+1"),
                   ("LR", 2, 2, N_("Move the head to the lower right corner of the design"), "Ctrl+3"))
        for key, r, c, tip, sc in corners:
            b = QPushButton()
            b.setIcon(icons.centre_icon() if key == "CC" else icons.corner_icon(key))
            b.setIconSize(QSize(JOG_ICON, JOG_ICON))
            b.setFixedSize(JOG_BUTTON, JOG_BUTTON)
            b.setToolTip("%s (%s).\n%s" % (_(tip), sc, _("The design does not move.")))
            b.clicked.connect(lambda _checked=False, k=key: self.move_to_corner(k))
            grid.addWidget(b, r, c)
            self.corner_buttons.append(b)
        pad = QHBoxLayout()
        pad.setContentsMargins(0, theme.SPACE_S, 0, theme.SPACE_L)
        pad.addStretch(1)
        pad.addLayout(machine)
        pad.addSpacing(theme.PAD_DIALOG + theme.SPACE_M)  # the machine's buttons apart from the jog pad
        pad.addLayout(grid)
        pad.addStretch(1)
        laser_layout.addLayout(pad)

        moves = QGridLayout()
        moves.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_L, 0)
        moves.setHorizontalSpacing(theme.SPACE_M)
        moves.setVerticalSpacing(theme.SPACE_M)
        self.jog_step = self._spin("jog_step", "len", 0.01, 1000, 2)
        self.jog_step.setToolTip(_("Distance moved by one arrow click"))
        fit_spin(self.jog_step, 999.99)
        moves.addWidget(widgets.caption("arrows-horizontal", _("Step"), self.jog_step.toolTip()), 0, 0)
        moves.addWidget(self.jog_step, 0, 1, 1, 2)
        # go to an absolute position (from home)
        self.goto_x = QDoubleSpinBox()
        self.goto_y = QDoubleSpinBox()
        for w, key, sign in ((self.goto_x, "gotoX", 1.0), (self.goto_y, "gotoY", -1.0)):
            w.setRange(0.0, 10000.0)
            w.setDecimals(2)
            w.setPrefix("X " if w is self.goto_x else "Y ")      # (docs/ui-mockups/LaserTab)
            w.setButtonSymbols(QDoubleSpinBox.NoButtons)       # typed in; they share the row's width
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            w.setMinimumWidth(theme.BUTTON_MIN_WIDTH)
            self._unit_widgets.append((w, "len", key, sign))
        try:
            self.goto_x.setValue(float(self.values.get("gotoX") or 0))
            self.goto_y.setValue(max(0.0, -float(self.values.get("gotoY") or 0)))
        except ValueError:
            pass
        self.goto_x.valueChanged.connect(lambda v: self._set_value("gotoX", _num_text(v)))
        # gotoY is stored like K40 Whisperer (up is positive); shown as distance down
        self.goto_y.valueChanged.connect(lambda v: self._set_value("gotoY", _num_text(-v)))
        self.goto_x.setToolTip(_("Distance right from home"))
        self.goto_y.setToolTip(_("Distance down from home"))
        self.btn_goto = QPushButton(_("Go"))
        self.btn_goto.setIcon(icons.tabler("arrow-right"))
        self.btn_goto.setToolTip(_("Home the head, then move to X/Y (%s)")
                                % self.act_goto.shortcut().toString(QKeySequence.NativeText))
        self.btn_goto.clicked.connect(self.goto_position)
        widgets.DialogFooter.style_button(self.btn_goto, "secondary")
        self.btn_goto.setMinimumWidth(0)
        self.btn_goto.setFixedHeight(theme.HEIGHT_FIELD)
        moves.addWidget(widgets.caption("current-location", _("Go to"), self.btn_goto.toolTip()), 1, 0)
        moves.addWidget(self.goto_x, 1, 1)
        moves.addWidget(self.goto_y, 1, 2)
        moves.addWidget(self.btn_goto, 1, 3)
        moves.setColumnStretch(1, 1)
        moves.setColumnStretch(2, 1)
        laser_layout.addLayout(moves)

        # test fire (M3 boards)
        self.test_fire_row = QWidget()
        row = QHBoxLayout(self.test_fire_row)
        row.setContentsMargins(theme.SPACE_L, theme.SPACE_L, theme.SPACE_L, 0)
        row.setSpacing(theme.SPACE_M)
        self.btn_test_fire = QPushButton(_("Test fire"))
        self.btn_test_fire.setIcon(icons.tabler("flame", theme.token("fire")))
        self.btn_test_fire.setToolTip(_("Fire the laser briefly (M3 boards)"))
        self.btn_test_fire.clicked.connect(self.test_fire)
        row.addWidget(self.btn_test_fire)
        row.addWidget(self._spin("test_power", "power", 0, 100, 0))
        t = self._spin("test_time", "int", 0, 1000)
        t.setSuffix(" ms")
        fit_spin(t, 1000)
        row.addWidget(t)
        row.addStretch(1)
        laser_layout.addWidget(self.test_fire_row)
        laser_layout.addStretch(1)

        # --- Design tab, Layers: the material, the layers' table, add a layer, the total time
        design_layout.addWidget(self._panel_header(_("Layers")))
        self.layers_panel = LayersPanel()
        self.layers_panel.changed.connect(self._layer_changed)
        self.layers_panel.structure_changed.connect(self._layers_structure_changed)
        self.layers_panel.add_layer.connect(self.add_layer)
        self.layers_panel.remove_layer.connect(self.remove_layer)
        self.layers_panel.material_chosen.connect(self.apply_material)
        self.layers_panel.manage_materials.connect(self.edit_materials)
        self.layers_panel.calc_raster.connect(self.calculate_raster_time)
        self.layers_panel.set_materials([m.name for m in self.materials])
        self.btn_calc_time = self.layers_panel.add_button       # disabled while busy, like before
        layers_box = QWidget()
        lv = QVBoxLayout(layers_box)
        lv.setContentsMargins(theme.SPACE_L, 0, theme.SPACE_L, 0)
        lv.addWidget(self.layers_panel)
        design_layout.addWidget(layers_box)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # only up and down: the panel is as wide as its content needs (PANEL_ROOM more than that, at least PANEL_WIDTH)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll = scroll
        # Trace, Start, Pause and Stop stay at the bottom, outside the scrolling part: on a small screen
        # (1366 x 768) the panel scrolls, and reaching Start with the wheel changed the speed fields
        # the wheel passed over (a user's report 2026-11-12)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(scroll, 1)
        footer = QFrame()
        footer.setObjectName("run_footer")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(theme.SPACE_L, theme.SPACE_L, theme.SPACE_L, theme.SPACE_L)
        footer_layout.setSpacing(theme.SPACE_M)
        self.bed_warning = QLabel()
        self.bed_warning.setObjectName("bed_warning")
        self.bed_warning.setWordWrap(True)
        self.bed_warning.hide()
        footer_layout.addWidget(self.bed_warning)
        # Engrave / Outline / Cut only (switched on in Settings → View): small, above Start, always visible
        self.kind_row = QWidget()
        kind_layout = QHBoxLayout(self.kind_row)
        kind_layout.setContentsMargins(0, 0, 0, 0)
        kind_layout.setSpacing(theme.SPACE_S)
        self.kind_buttons = {}
        for kind, act in self.act_run_kind.items():
            # a push button: its colour square and text are centred, not stuck to the left edge
            b = QPushButton(act.icon(), act.text())
            b.setObjectName("kind_button")
            b.clicked.connect(act.trigger)

            def follow(_b=b, _a=act):
                _b.setEnabled(_a.isEnabled())
                _b.setToolTip(_a.toolTip())
            act.changed.connect(follow)
            follow()
            b.setFixedHeight(theme.HEIGHT_FIELD)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            kind_layout.addWidget(b)
            self.kind_buttons[kind] = b
        self.kind_row.setVisible(is_true(self.values.get("kind_buttons", "0")))
        footer_layout.addWidget(self.kind_row)
        # the job's four buttons, as wide as each other (docs/ui-mockups/Main)
        run = QGridLayout()
        run.setSpacing(theme.SPACE_M)

        def job_button(name, icon, text, tip, slot):
            b = QPushButton(icon, text)
            b.setObjectName(name)
            b.setIconSize(QSize(theme.ICON, theme.ICON))
            b.setFixedHeight(theme.HEIGHT_ACTION)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumWidth(0)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b
        self.btn_trace = job_button("trace", icons.trace_icon(), C_("job", "Trace"),
                                    _("Trace boundary: move the head around the outline of the design "
                                      "(laser off unless set in Settings), to check where it will be cut"),
                                    lambda: self.start_job(trace=True))
        def on_colour(name):
            """White on the green / red button, grey while it is off (the button is grey then)."""
            icon = QIcon()
            for mode, ink in ((QIcon.Normal, "action_ink"), (QIcon.Disabled, "caption")):
                icon.addPixmap(icons.tabler(name, theme.token(ink)).pixmap(2 * theme.ICON, 2 * theme.ICON), mode)
            return icon
        self.btn_start = job_button("start", on_colour("player-play"), _("Start"),
                                    _("Start the selected operations") + " (F9)", lambda: self.start_job())
        self.btn_pause = job_button("pause", icons.tabler("player-pause"), C_("job", "Pause"),
                                    _("Pause the laser; press again to resume"), self.pause_job)
        self.btn_pause.setEnabled(False)
        self.btn_stop = job_button("stop", on_colour("player-stop"), _("Stop"),
                                   _("Stop the job now") + " (Esc)", self.stop_job)
        self.btn_stop.setEnabled(False)
        for n, b in enumerate((self.btn_trace, self.btn_start, self.btn_pause, self.btn_stop)):
            run.addWidget(b, 0, n)
            run.setColumnStretch(n, 1)
        footer_layout.addLayout(run)
        body_layout.addWidget(footer)
        self.run_footer = footer
        dock = QDockWidget(_("Job"), self)
        dock.setObjectName("job_dock")
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())             # no title bar: the tabs say what it is
        dock.setWidget(body)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [theme.PANEL_WIDTH], Qt.Horizontal)       # then _fit_panel_width: its content and PANEL_ROOM
        self.job_dock = dock
        for key in ("x", "y", "w", "h"):
            self._unit_widgets.append((self.sel_fields[key], "len", None, 1.0))
        self._update_unit_suffixes()

    def _build_status(self):
        # progress of the current step (filled by the percentages in the status messages) ...
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        # where the design under the mouse pointer (or the selected one) comes from: its folders and
        # file, to tell apart designs of the same name (one folder per customer, a user's request)
        self.path_label = QLabel()
        self.path_label.setObjectName("path_label")
        self.path_label.setTextFormat(Qt.PlainText)
        self.statusBar().addPermanentWidget(self.path_label)
        # ... and a small moving bar on its right: Kerfly is working
        self.busy_indicator = QProgressBar()
        self.busy_indicator.setRange(0, 0)
        self.busy_indicator.setTextVisible(False)
        self.busy_indicator.setFixedWidth(4 * self.fontMetrics().height())
        self.busy_indicator.hide()
        self.statusBar().addPermanentWidget(self.busy_indicator)
        # (docs/ui-mockups/Main) where the pointer is, the bed's size, the zoom, the laser's state
        self.status_pointer = widgets.hint("", wrap=False)
        self.status_bed = widgets.hint("", wrap=False)
        self.status_zoom = widgets.hint("", wrap=False)
        self.status_laser_dot = widgets.status_dot()
        self.status_laser = widgets.hint("", wrap=False)
        laser = QWidget()
        h = QHBoxLayout(laser)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(theme.SPACE_S + 2)
        h.addWidget(self.status_laser_dot)
        h.addWidget(self.status_laser)
        for n, w in enumerate((self.status_pointer, self.status_bed, self.status_zoom, laser)):
            if n:
                self.statusBar().addPermanentWidget(widgets.separator())
            self.statusBar().addPermanentWidget(w)
        self.preview.signals.pointer.connect(self._show_pointer)
        self.preview.signals.zoomed.connect(self._show_view_state)
        self._show_view_state()
        self.statusBar().showMessage(_("Ready"))

    def _show_pointer(self, x_mm, y_mm):
        """The pointer's place on the bed in the status bar, from home like the X and Y fields."""
        if is_true(self.values.get("HomeUR", "0")):          # (cheap: this runs on every mouse move)
            x_mm = config.bed_size_inches(self.values)[0] * 25.4 - x_mm
        scale = 1.0 if self.values.get("units") == "mm" else 1 / 25.4
        self.status_pointer.setText("X %s  Y %s %s" % (_num(x_mm * scale), _num(y_mm * scale),
                                                       self.values.get("units")))

    def _show_view_state(self):
        """The bed's size and the zoom (100 %: the whole bed fitted in the view) in the status bar."""
        bed_w, bed_h = config.bed_size_inches(self.values)
        self.status_bed.setText(_("Bed %s \u00d7 %s mm") % (_num(bed_w * 25.4, 0), _num(bed_h * 25.4, 0)))
        fitted = self.preview._fit_scale()
        if fitted:
            self.status_zoom.setText(_("Zoom %d%%") % round(100.0 * self.preview.transform().m11() / fitted))

    # ------------------------------------------------------------ state
    # ------------------------------------------------------------ elements
    @property
    def design(self):
        """The elements compiled into one design (cached until they change)."""
        from kerfly.core.layers import _signature, job_elements, layout_frame
        try:
            ur = bool(self.job_settings().home_upper_right)
        except ValueError:
            ur = False
        sig = (_signature(self.elements), ur)
        if self._compiled is None or self._compiled[2] != sig:
            # laid out as the job does it (home in the upper right: mirrored places), started
            # from the layout's corner on the bed
            design, _o = compile_layout(job_elements(self.elements, self.job_settings() if ur else None))
            _b, origin = layout_frame([e for e in self.elements if e.visible])
            self._compiled = (design or Design(), origin or (0.0, 0.0), sig,
                              [e.design for e in self.elements if e.visible])
        return self._compiled[0]

    @property
    def origin(self):
        """Bed position where the job starts (top-left of all elements)."""
        self.design
        return self._compiled[1]

    def _layout_changed(self):
        self._compiled = None
        self._layer_cache.clear()
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview()

    def _units_per_inch(self):
        return 25.4 if self.values.get("units", "mm") == "mm" else 1.0

    def _off_bed_elements(self):
        """Visible elements that stick out of the laser bed (they go into the job)."""
        bed_w, bed_h = config.bed_size_inches(self.values)
        return [e for e in self.elements if e.visible and not on_bed(e, bed_w, bed_h)]

    def _layout_fits_bed(self):
        return not self._off_bed_elements()

    def _update_bed_check(self):
        """Elements outside the bed are drawn red, and nothing can be sent to the
        laser (Start, Trace) until they are moved back."""
        off = self._off_bed_elements()
        busy = self.worker is not None
        self.bed_warning.setVisible(bool(off))
        if off:
            names = ", ".join(e.name for e in off[:3]) + ("…" if len(off) > 3 else "")
            self.bed_warning.setText(_("Outside the work area: %s. Move it onto the bed to start.") % names)
        for w in (self.btn_start, self.btn_trace, self.act_start, self.act_trace):
            w.setEnabled(not busy and not off)
        times = getattr(self, "_last_layer_times", {})
        for kind, act in getattr(self, "act_run_kind", {}).items():
            layers = [l for l in self.layers if l.kind == kind and l.enabled and self._layer_has_data(l)]
            act.setEnabled(not busy and not off and bool(layers))
            seconds = [times.get(l.id) for l in layers]
            tip = act.statusTip()
            if layers and all(t is not None for t in seconds):
                tip += " (%s)" % format_time(sum(seconds))
            act.setToolTip(tip)

    def _keep_on_bed(self, element):
        """Nudge an element back onto the bed if it fits there."""
        bed_w, bed_h = config.bed_size_inches(self.values)
        w, h = element.size
        if w <= bed_w:
            element.x = min(max(element.x, 0.0), bed_w - w)
        if h <= bed_h:
            element.y = max(min(element.y, 0.0), -bed_h + h)

    # ---- undo / redo: snapshots of the element list and placements ----
    def _snapshot(self):
        return (list(self.elements),
                [(e.placement(), e.design, e.shape.copy() if e.shape is not None else None,
                  dict(e.layers), e.group) for e in self.elements],
                self.selected,
                list(self.layers))                       # added / deleted layers come back too

    def _checkpoint(self):
        """Call before changing the layout."""
        self._set_dirty(True)
        self._undo.append(self._snapshot())
        del self._undo[:-100]
        self._redo.clear()

    def _restore(self, snap):
        elements, states, selected, layer_list = snap
        layers_changed = [id(l) for l in layer_list] != [id(l) for l in self.layers]
        self.layers = list(layer_list)
        self.elements = list(elements)
        for e, (placement, design, shape, part_layers, group) in zip(self.elements, states):
            e.set_placement(placement)
            e.design = design
            e.shape = shape
            e.layers = part_layers
            e.group = group
        self.selected = selected if selected in self.elements else None
        self._compiled = None
        self._layout_changed()
        if layers_changed:                               # a layer added or deleted in between
            self._rebuild_layers_panel()
        self._update_tool_options(force=True)

    def undo(self):
        if self._undo and self.worker is None:
            self._redo.append(self._snapshot())
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo and self.worker is None:
            self._undo.append(self._snapshot())
            self._restore(self._redo.pop())

    # ---- grid ----
    def _grid_mm(self):
        try:
            return max(0.0, float(self.values.get("grid_mm", "0") or 0))
        except ValueError:
            return 0.0

    def _grid_size_choice(self):
        """The grid size to switch on: the one in use, or the last one used."""
        try:
            last = float(self.values.get("grid_last_mm") or 5.0)
        except ValueError:
            last = 5.0
        return self._grid_mm() or (last if last > 0 else 5.0)

    def _remember_view(self):
        """Grid, snapping and "design follows the head" are kept for the next start at once
        (Kerfly's window.ini; tests and the self-test leave it alone)."""
        if getattr(self, "remember_geometry", False):
            from kerfly.gui import viewstate
            viewstate.save(self.values)

    def toggle_snap(self, checked):
        self.values["grid_mm"] = _num_text(self._grid_size_choice()) if checked else "0"
        self._remember_view()
        self.refresh_preview()

    def toggle_snap_objects(self, checked):
        self.values["snap_objects"] = "1" if checked else "0"
        self.preview.snap_objects = bool(checked)
        self.preview.hide_snap_marker()
        self._remember_view()

    def set_grid(self, mm):
        self.values["grid_last_mm"] = _num_text(mm)
        self.values["grid_mm"] = _num_text(mm)
        self.act_snap.setChecked(True)
        self._remember_view()
        self.refresh_preview()

    def _sync_view_actions(self):
        """The View menu and the follow-head button show the settings (after the Settings dialog)."""
        grid = self._grid_mm()
        if grid > 0:
            self.values["grid_last_mm"] = _num_text(grid)
        self.act_snap.setChecked(grid > 0)
        on = is_true(self.values.get("snap_objects", "1"))
        self.act_snap_objects.setChecked(on)
        self.preview.snap_objects = on
        self.act_follow_head.setChecked(is_true(self.values.get("follow_head", "0")))
        self._remember_view()

    def _snap(self, element):
        g = self._grid_mm() / 25.4
        if g > 0:
            element.x = round(element.x / g) * g
            element.y = round(element.y / g) * g

    # ---- element list ----
    def _element_path(self, e):
        """The file a design element came from ("" for shapes drawn in Kerfly and generated designs)."""
        if e is None:
            return ""
        path = e.origin or e.source_file or ""
        if path and os.path.basename(os.path.dirname(path)) == "generated":     # a stamp made by Kerfly
            from kerfly.core.materials import library_path
            if os.path.dirname(path) == os.path.join(os.path.dirname(library_path()), "generated"):
                return ""
        return path

    def _show_path(self, e):
        """The bottom bar: the folders and file of the design under the mouse pointer, else of
        the selected one (shortened in the middle; the whole path in the tooltip)."""
        if e is None:
            e = self.selected
        path = self._element_path(e)
        if not path:
            self.path_label.clear()
            self.path_label.setToolTip("")
            return
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        short = " / ".join(parts[-3:])                   # e.g. Desktop / Pg4 Zosi / PG-4-wnetrze-A.svg
        width = max(200, int(self.width() * 0.45))
        self.path_label.setText(self.path_label.fontMetrics().elidedText(short, Qt.ElideMiddle, width))
        self.path_label.setToolTip(path)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Leave and hasattr(self, "element_list") and obj is self.element_list.viewport():
            self._show_path(None)                        # left the list: back to the selected design
        return super().eventFilter(obj, event)

    def _update_element_list(self):
        from kerfly.core.groups import paths
        lst = self.element_list
        lst.blockSignals(True)
        numbers = {}
        rows = []
        for e in self.elements:
            name = e.name
            groups = []
            for path in paths(e.group):
                gid = path.rsplit("/", 1)[-1]
                if gid not in self.group_names and gid not in numbers:
                    numbers[gid] = len(numbers) + 1
                groups.append((path, self.group_names.get(gid) or _("Group %d") % numbers[gid]))
            kinds = [k for k in (RASTER, ENGRAVE, CUT, GCODE) if e.design is not None and part_present(e.design, k)]
            layers = [layer_of(e, k, self.layers) for k in kinds]
            layers = [l for l in layers if l is not None]
            path = self._element_path(e)
            if path:                                     # the folder too: designs of the same name differ
                name = "%s \u203a %s" % (os.path.basename(os.path.dirname(path)) or "/", name)
            rows.append((groups, (self._layer_swatch([l.color for l in layers]),
                                  "%s  \u00b7  %s" % (name, ", ".join(l.name for l in layers)) if layers else name,
                                  path, e.visible)))
        lst.fill(rows)
        lst.blockSignals(False)
        self._sync_list_selection()
        self.element_list_box.setVisible(bool(self.elements))      # also for a single element
        self.empty_state.setVisible(not self.elements)

    def _layer_swatch(self, colors):
        """Icon with a small square in each layer colour (like LightBurn's list)."""
        from PySide6.QtGui import QIcon, QPainter, QPixmap
        size = self.element_list.fontMetrics().height()
        pm = QPixmap(max(1, len(colors)) * (size + 2), size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        for n, c in enumerate(colors):
            p.fillRect(n * (size + 2) + 1, 1, size - 2, size - 2, QColor(c))
            p.setPen(QColor(theme.token("swatch_border")))
            p.drawRect(n * (size + 2) + 1, 1, size - 3, size - 3)
        p.end()
        return QIcon(pm)

    def _sync_list_selection(self):
        """Highlight the rows of the elements selected on the bed."""
        lst = self.element_list
        chosen = {id(e) for e in self.preview.selected_elements()}
        if not chosen and self.selected is not None:
            chosen = {id(self.selected)}
        lst.blockSignals(True)
        current = None
        for row, e in enumerate(self.elements):
            item = lst.item(row)
            if item is None:
                continue
            on = id(e) in chosen
            item.setSelected(on)
            if on and current is None:
                current = row
        for path, node in lst._groups.items():     # a group's row: all of it selected
            members = lst.members(path)
            node.setSelected(bool(members) and all(n < len(self.elements) and id(self.elements[n]) in chosen
                                                   for n in members))
        clicked = lst.currentItem()
        if clicked is not None and clicked.isSelected() and lst.group_of(clicked):
            current = None                           # a group's row picked: it stays the current row
        if current is not None:
            target = lst.item(current)               # in a shut group: its row (going to the row would open it)
            parent = target.parent()
            while parent is not None:
                if not parent.isExpanded():
                    target = parent
                parent = parent.parent()
            lst.setCurrentItem(target, 0, QItemSelectionModel.NoUpdate)
            lst.scrollToItem(target)
        lst.blockSignals(False)

    def _list_selection_changed(self):
        """Rows picked in the element list select those elements on the bed; a group's row its group alone
        (also a group inside a group)."""
        lst = self.element_list
        picked = lst.selectedItems()
        groups = [lst.group_of(i) for i in picked if lst.group_of(i)]
        rows = {lst.row(i) for i in picked if lst.row(i) >= 0}
        for path in groups:
            rows.update(lst.members(path))
        from kerfly.core.groups import ALONE
        if len(groups) == 1:
            self.preview.scope = groups[0]           # that group alone, not the one around it
        elif not groups and rows:
            self.preview.scope = ALONE               # elements' own rows: those elements alone
        else:
            self.preview.scope = ""
        chosen = [self.elements[r] for r in sorted(rows) if 0 <= r < len(self.elements)]
        self.preview.select_element(chosen)
        self.selected = chosen[0] if len(chosen) == 1 else None
        self._update_selection_panel()
        self._update_layer_assignment()
        self._update_tool_options()
        self._sync_list_selection()                  # a group member brings its whole group

    def _element_item_changed(self, item, _column=0):
        lst = self.element_list
        path = lst.group_of(item)
        if path:                                     # a group's tick: all of it in or out of the job
            visible = item.checkState() != Qt.Unchecked
            members = [self.elements[n] for n in lst.members(path) if n < len(self.elements)]
            if any(e.visible != visible for e in members):
                self._checkpoint()
                for e in members:
                    e.visible = visible
                self._layout_changed_soon()
            return
        row = lst.row(item)
        if 0 <= row < len(self.elements):
            visible = item.checkState() == Qt.Checked
            if self.elements[row].visible != visible:
                self._checkpoint()
                self.elements[row].visible = visible
                self._layout_changed_soon()

    def _layout_changed_soon(self):
        """_layout_changed() once the list's click is over: it fills the list again, and the row clicked must
        not go away while Qt still handles its click."""
        if not getattr(self, "_layout_pending", False):
            self._layout_pending = True

            def run():
                self._layout_pending = False
                self._layout_changed()
            QTimer.singleShot(0, run)

    # ---- more editing commands ----
    def duplicate_selected(self):
        chosen = self._selection()
        if not chosen or self.worker is not None:
            return
        self._checkpoint()
        new_groups = {}
        copies = []
        for src in chosen:
            e = src.copy()
            if e.group:                                  # a copied group is a new group
                e.group = self._renewed_group(e.group, new_groups, self.group_names)
            e.x += 5 / 25.4
            e.y -= 5 / 25.4
            copies.append(e)
        if len(copies) == 1:
            self._keep_on_bed(copies[0])
        self.elements.extend(copies)
        self.selected = copies[0] if len(copies) == 1 else None
        self._arranged(copies)

    def center_on_bed(self):
        """Centre the selected element, or all elements together, on the bed."""
        if not self.elements or self.worker is not None:
            return
        bed_w, bed_h = config.bed_size_inches(self.values)
        self._checkpoint()
        if self.selected is not None:
            self.selected.set_centre(bed_w / 2.0, -bed_h / 2.0)
        else:
            xmin = min(e.bounds[0] for e in self.elements)
            xmax = max(e.bounds[1] for e in self.elements)
            ymin = min(e.bounds[2] for e in self.elements)
            ymax = max(e.bounds[3] for e in self.elements)
            dx = bed_w / 2.0 - (xmin + xmax) / 2.0
            dy = -bed_h / 2.0 - (ymin + ymax) / 2.0
            for e in self.elements:
                e.x += dx
                e.y += dy
        self._layout_changed()

    def _preview_nudged(self, element, dx_mm, dy_mm):
        """Arrow keys in the bed view: move the selected element (screen directions)."""
        if self.worker is not None:
            return
        chosen = self._selection() or [element]
        self._checkpoint()
        sign = -1 if self.job_settings().home_upper_right else 1
        for e in chosen:
            e.x += sign * dx_mm / 25.4
            e.y += dy_mm / 25.4
        if len(chosen) == 1:
            self._keep_on_bed(chosen[0])
        self._arranged(chosen)

    def _preview_selected(self, element):
        self.selected = element
        self._update_selection_panel()
        self._update_layer_assignment()
        self._update_tool_options()
        self._sync_list_selection()
        self._show_path(None)                            # the selected design's folder and file, below

    def _preview_moved(self, element, dx, dy):
        """An element was dragged; the other selected elements (a group or a
        multiple selection) moved with it by the same amount."""
        chosen = self._selection()
        if element not in chosen:
            chosen = [element]
        if chosen == [element] and element.shape is not None and element.shape.kind == "text" \
                and element.shape.text_path and element.is_identity:
            # text on a path: dragging slides it along the path (it stays on the line)
            from kerfly.gui.text_shapes import slide_along_path
            sx = dx * 25.4 * (-1 if self.job_settings().home_upper_right else 1)
            sy = -dy * 25.4
            spec = element.shape.copy()
            spec.text_path_offset = slide_along_path(spec, sx, sy)
            self._apply_shape(element, spec)
            QTimer.singleShot(0, self, lambda: self._update_tool_options(force=True))
            return
        self._checkpoint()
        for e in chosen:
            e.x += dx
            e.y += dy
        if not self.preview.last_move_snapped and not self.preview.snap_suspended():
            # (snapped to another element: keep that, not the grid; Alt held: no snapping at all)
            x0, y0 = element.x, element.y
            self._snap(element)
            for e in chosen:
                if e is not element:
                    e.x += element.x - x0
                    e.y += element.y - y0
        self.preview.last_move_snapped = False
        if len(chosen) == 1:
            self._keep_on_bed(element)
        self._arranged(chosen)

    def _preview_scaled(self, element, factor):
        self._checkpoint()
        cx, cy = element.centre
        element.scale_x *= factor
        element.scale_y *= factor
        element.set_centre(cx, cy)
        self._keep_on_bed(element)
        self._layout_changed()

    def _preview_stretched(self, element, axis, factor, dx_mm, dy_mm):
        """A side handle was dragged: the element stretched along its own x or y, its centre moved by
        (dx_mm, dy_mm) on the bed view so the opposite side stays where it was."""
        self._checkpoint()
        cx, cy = element.centre
        if axis == "x":
            element.scale_x *= factor
        else:
            element.scale_y *= factor
        dx = dx_mm / 25.4 * (-1 if self.job_settings().home_upper_right else 1)
        element.set_centre(cx + dx, cy - dy_mm / 25.4)
        self._keep_on_bed(element)
        self._layout_changed()

    def _preview_rotated(self, element, degrees):
        self._rotate(element, degrees)

    def _rotate(self, element, degrees):
        self._checkpoint()
        cx, cy = element.centre
        element.rotation = (element.rotation + degrees) % 360
        if abs(element.rotation - round(element.rotation)) < 1e-6:
            element.rotation = float(round(element.rotation)) % 360
        element.set_centre(cx, cy)
        self._keep_on_bed(element)
        self._layout_changed()

    # ---- mirror, align, distribute -------------------------------------
    def _selection(self):
        """Elements selected in the bed view (several with a rubber band or
        Ctrl+click), with all members of their groups."""
        picked = {id(e) for e in self.preview.selected_elements()}
        # in the order of the element list (the bed view's order changes from run to run, and a
        # union of the same shapes then started its outline elsewhere)
        chosen = [e for e in self.elements if id(e) in picked]
        if not chosen and self.selected is not None:
            chosen = [self.selected]
        from kerfly.core.groups import unit_of, within
        units = {unit_of(e.group, self.preview.scope) for e in chosen if e.group}
        if units:
            chosen = [e for e in self.elements if e in chosen or any(within(e.group, u) for u in units)]
        return chosen

    def reorder_selected(self, how):
        """Move the selected elements (with their groups) in the element list,
        which is the order of the job: "up" / "first" earlier, "down" / "last"
        later (later elements also lie on top in the bed view)."""
        if self.worker is not None:
            return
        how = {"up": "backward", "down": "forward", "first": "back", "last": "front"}.get(how, how)
        chosen = self._selection()
        if not chosen:
            self.status(_("Select the elements to move up or down first."), error=True)
            return
        picked = [e in chosen for e in self.elements]
        order = list(self.elements)
        if how == "front":
            order = [e for e, p in zip(order, picked) if not p] + [e for e, p in zip(order, picked) if p]
        elif how == "back":
            order = [e for e, p in zip(order, picked) if p] + [e for e, p in zip(order, picked) if not p]
        else:
            flags = list(picked)
            rng = range(len(order) - 2, -1, -1) if how == "forward" else range(1, len(order))
            for i in rng:
                j = i + 1 if how == "forward" else i - 1
                if flags[i] and not flags[j]:
                    order[i], order[j] = order[j], order[i]
                    flags[i], flags[j] = flags[j], flags[i]
        if order == self.elements:
            self.status(_("Already at the end of the list.") if how in ("forward", "front")
                        else _("Already at the start of the list."))
            return
        self._checkpoint()
        self.elements = order
        self._compiled = None
        self._layer_cache.clear()
        self._layout_changed()
        self.preview.select_element(chosen)

    # ---- generators ----------------------------------------------------------
    def open_generator(self, key):
        """Ask for a generator's numbers (with a preview), then insert the design."""
        from kerfly.gui.generators import GeneratorDialog
        if self.worker is not None:
            return
        dlg = GeneratorDialog(self, key, remember=getattr(self, "remember_geometry", False))
        if dlg.exec():
            self.insert_generated(dlg.result_design())

    def insert_generated(self, design):
        """Put a generated design on the bed at the laser head, as one group and one undo
        step, with the layers it brings along."""
        from kerfly.core.generators import KIND_OF_OPERATION
        if not design.items:
            return []
        self._checkpoint()
        layer_of_key = {}
        for spec in design.layers:
            layer = Layer(spec.kind, name=spec.name, color=spec.color or EXTRA_COLORS[0],
                          speed=spec.speed, passes=int(spec.passes), power=spec.power,
                          enabled=getattr(spec, "enabled", True))
            index = max(i for i, l in enumerate(self.layers) if l.kind == spec.kind) + 1
            self.layers.insert(index, layer)
            layer_of_key[spec.key] = layer
        group = self._new_group_id() if len(design.items) > 1 else ""
        if group:
            self.group_names[group] = _(design.name)
        inner = {}                                       # groups inside its group (a box's sheets, parts)

        def group_of(item):
            path, key = group, ()
            if not group:
                return ""
            for level, name in item.group:
                key += (level,)
                if key not in inner:
                    inner[key] = self._new_group_id()
                    self.group_names[inner[key]] = name
                path += "/" + inner[key]
            return path
        hx, hy = self.head
        made = []
        for item in design.items:
            if item.image is not None:                   # a picture (stamp): saved, then opened as an image
                path = self._save_generated_image(item.image, design.name)
                built = Design()
                loaders.load_image(path, built, item.dpi, is_true(self.values.get("reduced_mem", "0")))
                e = Element(built, name=_(item.name or design.name), source_file=path,
                            load_options={"dpi": item.dpi}, group=group_of(item))
                e.x, e.y = hx + item.left / 25.4, hy - item.top / 25.4
                made.append((item, e))
                continue
            spec = item.spec.copy()
            if spec.kind == "text":
                update_text_spec(spec)
            elif spec.kind == "path" and spec.subpaths:          # nodes from (0, 0) of the outline
                from kerfly.core import curves
                spec.subpaths = curves.normalized(spec.subpaths)[0]
            built = build_design(spec)
            xmin, xmax, ymin, ymax = built.bounds
            if xmax - xmin <= 0 and ymax - ymin <= 0:
                continue
            e = Element(built, name=_(item.name) if item.name else _(KIND_NAMES.get(spec.kind, "Path")),
                        shape=spec, group=group_of(item))
            e.x, e.y = hx + item.left / 25.4, hy - item.top / 25.4
            e.visible = getattr(item, "active", True)        # a box's later sheets: unticked until their turn
            if item.layer in layer_of_key:
                e.layers[KIND_OF_OPERATION.get(spec.operation, CUT)] = layer_of_key[item.layer].id
            made.append((item, e))
        for item, e in made:                             # texts that run along another shape
            if item.on_path_of >= 0 and item.on_path_of < len(design.items):
                guide = next((g for it, g in made if it is design.items[item.on_path_of]), None)
                if guide is not None:
                    self._place_on_path(e, guide)
        elements = [e for _item, e in made]
        self.elements.extend(elements)
        self._shift_onto_bed(elements)
        self.selected = None
        self._compiled = None
        self._layer_cache.clear()
        self._rebuild_layers_panel()
        self._layout_changed()
        self.preview.select_element(elements)
        self.status(_("%(name)s inserted: %(n)d shapes. Drag it into place; Undo takes it away.")
                    % {"name": _(design.name), "n": len(elements)})
        return elements

    def _save_generated_image(self, image, name):
        """Keep a generated picture (e.g. a stamp) in Kerfly's settings folder, so the
        element can be reloaded and saved in projects like any opened picture."""
        import time
        from kerfly.core.materials import library_path
        folder = os.path.join(os.path.dirname(library_path()), "generated")
        os.makedirs(folder, exist_ok=True)
        base = "%s-%s" % (name.lower().replace(" ", "-"), time.strftime("%Y%m%d-%H%M%S"))
        path = os.path.join(folder, base + ".png")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(folder, "%s-%d.png" % (base, n))
        image.save(path)
        return path

    def _shift_onto_bed(self, elements):
        """Move elements together so all of them lie on the bed, if they fit."""
        if not elements:
            return
        bed_w, bed_h = config.bed_size_inches(self.values)
        x0 = min(e.bounds[0] for e in elements)
        x1 = max(e.bounds[1] for e in elements)
        y0 = min(e.bounds[2] for e in elements)
        y1 = max(e.bounds[3] for e in elements)
        dx = -x0 if x0 < 0 else min(0.0, bed_w - x1)
        dy = -y1 if y1 > 0 else max(0.0, -bed_h - y0)
        if x1 - x0 > bed_w:
            dx = -x0
        if y1 - y0 > bed_h:
            dy = -y1
        for e in elements:
            e.x += dx
            e.y += dy

    def _new_group_id(self):
        import uuid
        return uuid.uuid4().hex[:8]

    def _renewed_group(self, group, new_ids, names):
        """A copy of `group` with new ids (each copied group is a new group), keeping their names."""
        from kerfly.core.groups import ids, renamed
        for gid in ids(group):
            if gid not in new_ids:
                new_ids[gid] = self._new_group_id()
                if gid in names:
                    self.group_names[new_ids[gid]] = names[gid]
        return renamed(group, new_ids)

    def group_selected(self):
        from kerfly.core.groups import common, wrap
        chosen = self._selection()
        if len(chosen) < 2 or self.worker is not None:
            self.status(_("Select two or more elements to group them."), error=True)
            return
        self._checkpoint()
        gid = self._new_group_id()
        inside = common([e.group for e in chosen])
        if inside and all(e in chosen for e in self.elements if e.group.startswith(inside + "/") or e.group == inside):
            inside = inside.rsplit("/", 1)[0] if "/" in inside else ""     # the whole group: around it
        for e in chosen:
            e.group = wrap(e.group, inside, gid)
        self._arranged(chosen)
        self.status(_("Grouped %d elements. Click any of them to select the whole group.") % len(chosen))

    def ungroup_selected(self):
        from kerfly.core.explode import has_vectors

        def splittable(e):
            return (e.shape is None or e.shape.kind == "text") and e.design is not None and has_vectors(e.design)
        if not self._selection():                      # nothing selected: the only file or group is meant
            files_all = [e for e in self.elements if splittable(e) and not e.group]
            groups = {e.group for e in self.elements if e.group}
            if len(files_all) + len(groups) == 1:
                target = files_all or [e for e in self.elements if e.group]
                self.preview.select_element(target)
        selection = self._selection()
        files = [e for e in selection if splittable(e)]
        pictures = [e for e in selection if e.shape is None and e.design is not None
                    and e.design.raster.image is not None]
        if (files or pictures) and self.worker is None:
            # an opened file splits into one shape per line, and its picture into its separate parts
            for e in selection:
                if e not in files and e.group:
                    e.group = ""
            n_before = len(self.elements)
            if files:
                self.preview.select_element(files)
                self.break_apart_selected(grouped=False)
            pieces = self._split_pictures([e for e in pictures if e in self.elements], checkpoint=not files)
            if pieces:
                self._layout_changed()
                self.preview.select_element(pieces)
            made = len(self.elements) - n_before + len(files) + (len([e for e in pictures if e not in files])
                                                                  if pieces else 0)
            if files or pieces:
                self.status(_("Ungrouped into %d shapes: click one to move it, double-click it to edit its "
                              "nodes.") % made)
            return
        from kerfly.core.groups import unit_of, without
        chosen = [e for e in self._selection() if e.group]
        if not chosen or self.worker is not None:
            self.status(_("Click the opened file or the group first, then Ungroup."), error=True)
            return
        self._checkpoint()
        from kerfly.core.groups import ALONE
        if self.preview.scope == ALONE:              # elements picked alone: out of their group, one level
            for e in chosen:
                e.group = e.group.rsplit("/", 1)[0] if "/" in e.group else ""
        else:
            units = {unit_of(e.group, self.preview.scope) for e in chosen}
            for e in chosen:                         # one level: the groups inside stay groups
                for u in units:
                    e.group = without(e.group, u)
        self.preview.scope = ""
        self._arranged(chosen)

    def _arranged(self, chosen):
        """Finish an arrange command: redraw and keep the selection."""
        self._layout_changed()
        if len(chosen) > 1:
            self.preview.select_element(chosen)
            self._update_element_list()

    def mirror_selected(self, horizontal):
        chosen = self._selection()
        if not chosen or self.worker is not None:
            return
        self._checkpoint()
        if len(chosen) == 1:
            mirror(chosen[0], horizontal)
        else:
            x0, x1, y0, y1 = selection_bounds(chosen)
            mirror_about(chosen, horizontal, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
        self._arranged(chosen)

    def align_selected(self, edge):
        chosen = self._selection()
        if not chosen or self.worker is not None:
            return
        parts = units(chosen)
        if len(parts) == 1:
            bed_w, bed_h = config.bed_size_inches(self.values)
            frame = (0.0, bed_w, -bed_h, 0.0)
        else:
            frame = selection_bounds(chosen)
        self._checkpoint()
        align(parts, edge, frame)
        self._arranged(chosen)

    def distribute_selected(self, horizontal):
        chosen = self._selection()
        parts = units(chosen)
        if len(parts) < 3 or self.worker is not None:
            self.status(_("Select three or more elements to distribute them."), error=True)
            return
        self._checkpoint()
        how, step = distribute(parts, horizontal)
        if how == "in_line":
            self._undo.pop()                            # nothing changed
            self.act_undo.setEnabled(bool(self._undo))
            self.status(_("These elements are centred on one line in this direction, so there is nothing to "
                          "spread. Use the other direction, or move one of them first."), error=True)
            return
        self._arranged(chosen)
        unit = self.values.get("units", "mm")
        value = step * (25.4 if unit == "mm" else 1.0)
        if how == "gap":
            self.status(_("Distributed %d elements: gaps of %.2f %s between them.") % (len(parts), value, unit))
        else:
            self.status(_("Distributed %d elements: they are too wide for gaps, so their centres are "
                          "%.2f %s apart.") % (len(parts), value, unit))

    def rotate_selected(self, degrees):
        chosen = self._selection()
        if not chosen or self.worker is not None:
            return
        if len(chosen) == 1:
            self._rotate(chosen[0], degrees)
            return
        self._checkpoint()
        x0, x1, y0, y1 = selection_bounds(chosen)
        rotate_about(chosen, degrees, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
        self._arranged(chosen)

    def delete_selected(self):
        chosen = self._selection()
        if not chosen or self.worker is not None:
            return
        self._checkpoint()
        for e in chosen:
            self.elements.remove(e)
        self.selected = None
        self._multi = []
        self._layout_changed()

    # ---- right-click menu on the bed ----------------------------------------
    def _element_at(self, scene_point):
        """The topmost element drawn at a point of the bed view, or None. Looked up in
        the bed view's own list of element items: asking the scene (scene().items())
        made PySide delete the bed's white rectangle when the answer was dropped."""
        by_element = {id(i.element): i for i in self.preview._items}
        for e in reversed(self.elements):                 # later elements lie on top
            item = by_element.get(id(e))
            if item is not None and item.isVisible() and item.contains(item.mapFromScene(scene_point)):
                return e
        return None

    def _bed_context_menu(self, scene_point, global_pos):
        """Right click on the bed: the commands for the element under the pointer
        (it is selected first, unless it is already among the selected ones), or
        for the empty bed. The menu does not block the window (popup)."""
        from PySide6.QtWidgets import QMenu
        if self.worker is not None:
            return
        menu = QMenu(self)
        menu.setObjectName("bed_context_menu")
        e = self._element_at(scene_point)
        if e is not None:
            if e not in self._selection():
                self.preview.select_element(e)
                self.selected = e
            chosen = self._selection()
            for a in (self.act_cut, self.act_copy, self.act_paste, self.act_duplicate, self.act_delete):
                menu.addAction(a)
            menu.addSeparator()
            if len(chosen) > 1:
                menu.addAction(self.act_group)
            if any(c.group for c in chosen):
                menu.addAction(self.act_ungroup)
            self._layer_submenu(menu, chosen)
            if len(chosen) > 1:
                sub = menu.addMenu(_("Combine shapes"))
                for a in self.act_boolean.values():
                    sub.addAction(a)
            menu.addAction(self.act_join)
            menu.addAction(self.act_offset)
            sub = menu.addMenu(_("Order"))
            for a in self.act_order.values():
                sub.addAction(a)
            if len(chosen) > 1:
                sub = menu.addMenu(_("Align and distribute"))
                for a in list(self.act_align.values()) + [self.act_distribute_h, self.act_distribute_v]:
                    sub.addAction(a)
            menu.addSeparator()
            for a in (self.act_rot_left, self.act_rot_right, self.act_mirror_h, self.act_mirror_v):
                menu.addAction(a)
            menu.addSeparator()
            menu.addAction(self.tool_actions["fill"])
            if len(chosen) == 1 and e.shape is not None:
                menu.addAction(self.tool_actions["nodes"])
            if len(chosen) == 2:
                menu.addAction(self.act_text_path)
            menu.addAction(self.act_center)
            menu.addAction(self.act_nest)
            out = menu.addAction(_("Leave out of the job"))
            out.setCheckable(True)
            out.setChecked(all(not c.visible for c in chosen))
            out.setStatusTip(_("The elements stay on the bed but are not sent to the laser (as the tick of the "
                               "element list)"))
            out.triggered.connect(lambda checked, c=chosen: self._leave_out(c, checked))
        else:
            here = menu.addAction(icons.tabler("current-location"), _("Move the head here"))
            here.setStatusTip(_("Move the laser head to this point of the bed (the design stays where it is)"))
            try:
                bed = self._bed_point(scene_point)
            except ValueError:
                bed = None
            here.setEnabled(self.laser.connected and bed is not None)
            here.triggered.connect(lambda _c=False, p=bed: self._move_head_here(p))
            menu.addSeparator()
            for a in (self.act_paste, self.act_select_all, self.act_fit, self.act_snap):
                menu.addAction(a)
        self._context_menu = menu                     # for the tests
        menu.aboutToHide.connect(menu.deleteLater)    # a new menu every time: nothing left behind
        menu.popup(global_pos)

    def _layer_submenu(self, menu, chosen):
        """Layer ▸ the layers of the kinds the selected elements have (one click moves them)."""
        kinds = [k for k in (RASTER, ENGRAVE, CUT, GCODE) if any(part_present(c.design, k) for c in chosen)]
        if not kinds:
            return
        sub = menu.addMenu(_("Layer"))
        sub.setObjectName("layer_submenu")
        for n, kind in enumerate(kinds):
            if n:
                sub.addSeparator()
            sub.addSection(_(LAYER_KIND_NAMES[kind]))
            current = {layer_of(c, kind, self.layers).id for c in chosen if part_present(c.design, kind)}
            for layer in [l for l in self.layers if l.kind == kind]:
                pix = QPixmap(14, 14)
                pix.fill(QColor(layer.color))
                a = sub.addAction(QIcon(pix), layer.name or _(LAYER_KIND_NAMES[kind]))
                a.setCheckable(True)
                a.setChecked(current == {layer.id})
                a.triggered.connect(lambda _c=False, l=layer, c=chosen: self._move_to_layer(c, l))

    def _move_to_layer(self, elements, layer):
        """Put the parts of this layer's kind of the elements on the layer (one undo step)."""
        movable = [e for e in elements if part_present(e.design, layer.kind)]
        if not movable or self.worker is not None:
            return
        self._checkpoint()
        default = self._default_layer[layer.kind].id
        for e in movable:
            if layer.id == default:
                e.layers.pop(layer.kind, None)
            else:
                e.layers[layer.kind] = layer.id
        self._layer_cache.clear()
        self._rebuild_layers_panel()
        self._update_layer_assignment()
        self.refresh_preview()
        self.status(_("On the layer %s: %d element(s).") % (layer.name, len(movable)))

    def _leave_out(self, elements, out):
        self._checkpoint()
        for e in elements:
            e.visible = not out
        self._layout_changed()
        self._update_element_list()

    def _move_head_here(self, bed_point):
        bed_w, bed_h = config.bed_size_inches(self.values)
        x = min(max(bed_point[0], 0.0), bed_w)
        y = max(min(bed_point[1], 0.0), -bed_h)
        self.move_head_to(x, y, follow=False)

    # ---- clipboard ----------------------------------------------------------
    def copy_selected(self):
        """Copy the selected elements (with their groups) for Paste, also into
        another project in this window. Their layers go along by name."""
        chosen = self._selection()
        if not chosen:
            self.status(_("Select the elements to copy first."), error=True)
            return False
        names = {l.id: (l.kind, l.name) for l in self.layers}
        self._clipboard = ([e.copy() for e in chosen],
                           [{kind: names.get(lid) for kind, lid in e.layers.items()} for e in chosen],
                           dict(self.group_names))
        self._paste_count = 0
        self.status(_("Copied: %d element(s).") % len(chosen))
        return True

    def cut_selected(self):
        if self.worker is not None:
            return
        if self.copy_selected():
            n = len(self._clipboard[0])
            self.delete_selected()
            self.status(_("Cut: %d element(s).") % n)

    def paste(self, in_place=False):
        """Paste copies of the copied elements: at the mouse pointer when it is over
        the bed, otherwise 5 mm further than the last paste (in place: exactly
        where they were). Groups stay groups (new ones); layers by name and kind."""
        from kerfly.core.layout import selection_bounds
        if self.worker is not None:
            return
        if self._clipboard is None:
            self.status(_("Nothing copied yet: select elements and press Ctrl+C."), error=True)
            return
        originals, layer_names, group_names = self._clipboard
        new_groups = {}
        made = []
        for c, wanted in zip(originals, layer_names):
            e = c.copy()
            if e.group:
                e.group = self._renewed_group(e.group, new_groups, group_names)
            layers = {}
            for kind, name in wanted.items():
                same = [l for l in self.layers if (l.kind, l.name) == name and l.kind == kind]
                if same:
                    layers[kind] = same[0].id
            e.layers = layers
            made.append(e)
        if not in_place:
            xmin, xmax, ymin, ymax = selection_bounds(made)
            target = self._mouse_on_bed()
            if target is not None:
                dx, dy = target[0] - (xmin + xmax) / 2.0, target[1] - (ymin + ymax) / 2.0
            else:
                self._paste_count += 1
                dx, dy = 5 / 25.4 * self._paste_count, -5 / 25.4 * self._paste_count
            for e in made:
                e.x += dx
                e.y += dy
            self._keep_together_on_bed(made)
        self._checkpoint()
        self.elements.extend(made)
        self.selected = made[0] if len(made) == 1 else None
        self._compiled = None
        self._layer_cache.clear()
        self._arranged(made)
        if len(made) == 1:
            self.preview.select_element(made[0])
        self.status(_("Pasted: %d element(s).") % len(made))

    def _mouse_on_bed(self):
        """The bed position (inches) under the mouse pointer, or None when it is not over the bed view."""
        from PySide6.QtGui import QCursor
        vp = self.preview.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        if not vp.rect().contains(pos):
            return None
        try:
            return self._bed_point(self.preview.mapToScene(pos))
        except ValueError:
            return None

    def _keep_together_on_bed(self, elements):
        """Move elements together back onto the bed, if they fit there."""
        from kerfly.core.layout import selection_bounds
        bed_w, bed_h = config.bed_size_inches(self.values)
        xmin, xmax, ymin, ymax = selection_bounds(elements)
        dx = dy = 0.0
        if xmax - xmin <= bed_w:
            dx = -xmin if xmin < 0 else (bed_w - xmax if xmax > bed_w else 0.0)
        if ymax - ymin <= bed_h:
            dy = -ymax if ymax > 0 else (-bed_h - ymin if ymin < -bed_h else 0.0)
        for e in elements:
            e.x += dx
            e.y += dy

    def select_all(self):
        if self.elements:
            self.preview.select_element(list(self.elements))
            self._update_element_list()

    def deselect(self):
        self.preview.select_element([])
        self.selected = None
        self._update_element_list()

    def place_at_head(self):
        """Move all elements together so the design's top-left is at the laser head."""
        self._design_to_head(checkpoint=True)

    def home_corner(self):
        """The corner of the bed the head homes to (a laser's settings): "UL", "UR", "LL" or "LR"."""
        if self.is_grbl():
            from kerfly.gui.settings_dialog import GRBL_CORNERS
            return GRBL_CORNERS.get(self.values.get("grbl_home", "lower_left"), "LL")
        return ("L" if is_true(self.values.get("home_lower", "0")) else "U") + \
            ("R" if is_true(self.values.get("HomeUR", "0")) else "L")

    def _design_to_head(self, checkpoint):
        """The design's corner at the machine's home corner goes to the head (e.g. its lower left for a laser
        homing to the lower left). A K40's x runs from home (also from an upper right one): its origin is
        already on the home side."""
        if not self.elements or self.worker is not None:
            return
        ox, oy = self.origin
        corner = self.home_corner()
        shown = [e for e in self.elements if e.visible] or self.elements
        if corner[0] == "L":
            oy = min(e.bounds[2] for e in shown)
        if corner[1] == "R" and self.is_grbl():
            ox = max(e.bounds[1] for e in shown)
        if (ox, oy) == self.head:
            return
        if checkpoint:
            self._checkpoint()
        self._shift_design(self.head[0] - ox, self.head[1] - oy)

    def _shift_design(self, dx, dy):
        """Move all elements together by (dx, dy) inches (the elements' and the head's x both run away from
        home, also with an upper-right home)."""
        if not (dx or dy):
            return
        for e in self.elements:
            e.x += dx
            e.y += dy
        self._compiled = None
        self._layout_changed()

    def follow_head(self):
        return self.act_follow_head.isChecked()

    def toggle_follow_head(self, on):
        """Design follows the head: switching it on brings the design to the head."""
        self._set_value("follow_head", "1" if on else "0")
        self._remember_view()
        if on:
            self.place_at_head()
            self.status(_("The design now moves with the laser head."))
        else:
            self.status(_("The design stays in place when the laser head moves."))

    def _update_selection_panel(self):
        e = self.selected
        self.selection_box.setEnabled(e is not None)
        k = self._units_per_inch()
        values = {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
        rotation = 0.0
        if e is not None:
            w, h = e.size
            values = {"x": e.x * k, "y": -e.y * k, "w": w * k, "h": h * k}
            rotation = e.rotation if e.rotation <= 180 else e.rotation - 360
            self.selection_box.setToolTip(e.name)
        else:
            self.selection_box.setToolTip(_("Click an element on the bed to select it."))
        for key, spin in self.sel_fields.items():
            spin.blockSignals(True)
            spin.setValue(values[key])
            spin.blockSignals(False)
        self.sel_rotation.blockSignals(True)
        self.sel_rotation.setValue(rotation)
        self.sel_rotation.blockSignals(False)

    def _selection_field_changed(self, key):
        e = self.selected
        if e is None:
            return
        k = self._units_per_inch()
        if key in ("w", "h") and self.sel_fields[key].value() <= 0 < e.size[0 if key == "w" else 1]:
            self._update_selection_panel()           # 0 would flatten the element: keep its size
            return
        if key != "rotation":
            self._checkpoint()
        if key == "x":
            e.x = self.sel_fields["x"].value() / k
        elif key == "y":
            e.y = -self.sel_fields["y"].value() / k
        elif key in ("w", "h"):
            w, h = e.size
            new_w = self.sel_fields["w"].value() / k
            new_h = self.sel_fields["h"].value() / k
            if self.sel_lock.isChecked() and w > 0 and h > 0:
                factor = new_w / w if key == "w" else new_h / h
                new_w, new_h = w * factor, h * factor
            x, y = e.x, e.y                      # keep the top-left corner
            e.set_size(new_w, new_h)
            e.x, e.y = x, y
            self._keep_on_bed(e)
        elif key == "rotation":
            self._rotate(e, self.sel_rotation.value() - (e.rotation if e.rotation <= 180 else e.rotation - 360))
            return
        self._layout_changed()

    # ------------------------------------------------------------ layers
    def _init_layers(self):
        self.layers = []
        for kind in KINDS:
            layer = Layer(kind, name=_(LAYER_KIND_NAMES[kind]))
            from kerfly.core.layers import DEFAULT_COLORS
            layer.color = DEFAULT_COLORS[kind]
            self.layers.append(layer)
            self._default_layer[kind] = layer
        self._layers_from_values()

    def _layers_from_values(self):
        """Default layers take their settings from the K40 Whisperer settings values."""
        for kind, layer in self._default_layer.items():
            inc, feed, passes, power = DEFAULT_LAYER_KEYS[kind]
            layer.enabled = is_true(self.values.get(inc, "1"))
            try:
                if feed:
                    layer.speed = float(self.values.get(feed) or layer.speed)
                layer.passes = int(float(self.values.get(passes) or 1))
                layer.power = float(self.values.get(power) or 0.5)
                if kind == CUT:
                    layer.kerf = max(0.0, float(self.values.get("cut_kerf") or 0.0))
            except ValueError:
                pass

    def _layer_to_values(self, layer):
        if self._default_layer.get(layer.kind) is not layer:
            return
        inc, feed, passes, power = DEFAULT_LAYER_KEYS[layer.kind]
        self.values[inc] = "1" if layer.enabled else "0"
        if feed:
            self.values[feed] = _num_text(layer.speed)
        self.values[passes] = str(int(layer.passes))
        self.values[power] = _num_text(layer.power)
        if layer.kind == CUT:
            self.values["cut_kerf"] = _num_text(layer.kerf)

    def _layer_changed(self, layer):
        self._set_dirty(True)
        self._layer_to_values(layer)
        self._update_times()
        self.refresh_preview()

    def _layers_structure_changed(self):
        self._set_dirty(True)
        self._layer_cache.clear()
        self._rebuild_layers_panel()
        self.refresh_preview()

    def _layer_has_data(self, layer):
        return any(e.visible and layer_of(e, layer.kind, self.layers) is layer and part_present(e.design, layer.kind)
                   for e in self.elements)

    def _rebuild_layers_panel(self):
        gcode_file = any(part_present(e.design, GCODE) for e in self.elements)
        self.layers_panel.rebuild(self.layers, self._layer_has_data,
                                  lambda layer: self._default_layer.get(layer.kind) is not layer,
                                  config.speed_unit(self.values), self.power_per_stage(), gcode_file,
                                  config.speed_factor(self.values))
        self._update_times()
        self._fit_panel_width()

    def add_layer(self, kind):
        """Append a new layer of a kind to the list. Elements are moved to it with
        the Layer choice above the bed view (adding never takes a part away from
        the layer it is on)."""
        base = self._default_layer[kind]
        n = sum(1 for layer in self.layers if layer.kind == kind) + 1
        layer = Layer(kind, name="%s %d" % (_(LAYER_KIND_NAMES[kind]), n),
                      color=EXTRA_COLORS[(len(self.layers) - len(KINDS)) % len(EXTRA_COLORS)],
                      speed=base.speed, passes=base.passes, power=base.power)
        index = max(i for i, l in enumerate(self.layers) if l.kind == kind) + 1
        self._checkpoint()                               # Undo takes the new layer away again
        self.layers.insert(index, layer)
        self._layers_structure_changed()
        self._update_layer_assignment()
        return layer

    def remove_layer(self, layer):
        if self._default_layer.get(layer.kind) is layer:
            return
        self._checkpoint()
        for e in self.elements:
            if e.layers.get(layer.kind) == layer.id:
                del e.layers[layer.kind]
        self.layers.remove(layer)
        self._layers_structure_changed()
        self._update_layer_assignment()

    def _speed_from_mm_s(self, speed):
        return speed if self.values.get("units", "mm") == "mm" else speed * 60.0 / 25.4

    def _speed_to_mm_s(self, speed):
        return speed if self.values.get("units", "mm") == "mm" else speed * 25.4 / 60.0

    def apply_material(self, index):
        """Set every layer's speed, passes and power from a material."""
        if not 0 <= index < len(self.materials):
            return
        m = self.materials[index]

        def set_layer(layer, speed, passes, power, kerf):
            layer.speed = round(self._speed_from_mm_s(speed), 2)
            layer.passes = passes
            layer.power = power
            if layer.kind == CUT:
                layer.kerf = kerf
            self._layer_to_values(layer)
        extra = m.extra_layers
        if extra is not None:
            self._checkpoint()                           # layers it adds go away with Undo
        for layer in self.layers:
            s = m.get(layer.kind)
            if s is None:
                continue
            if extra is not None and self._default_layer.get(layer.kind) is not layer:
                continue                                 # the other layers: by their name, below
            set_layer(layer, s.speed, s.passes, s.power, s.kerf)
        for x in extra or []:
            # the material's other layers: the layer of the same kind and name, else a new one
            layer = next((l for l in self.layers if l.kind == x.kind and l.name == x.name
                          and self._default_layer.get(l.kind) is not l), None)
            if layer is None:
                layer = Layer(x.kind, name=x.name, color=x.color or EXTRA_COLORS[0])
                index_after = max(i for i, l in enumerate(self.layers) if l.kind == x.kind) + 1
                self.layers.insert(index_after, layer)
            set_layer(layer, x.speed, x.passes, x.power, x.kerf)
        self._layer_cache.clear()
        self._rebuild_layers_panel()
        self.layers_panel.material.setCurrentIndex(index + 1)
        self.status(_("Material: %s") % m.name)

    def edit_materials(self):
        current = {}
        for kind in (CUT, ENGRAVE, RASTER):
            layer = self._default_layer[kind]
            current[kind] = material_lib.OperationSettings(round(self._speed_to_mm_s(layer.speed), 2),
                                                           layer.passes, layer.power, layer.kerf)
        extra = [material_lib.ExtraLayer(l.kind, l.name, l.color, round(self._speed_to_mm_s(l.speed), 2),
                                         l.passes, l.power, l.kerf)
                 for l in self.layers if l.kind in (CUT, ENGRAVE, RASTER) and self._default_layer.get(l.kind) is not l]
        dlg = MaterialsDialog(self.materials, current, self.values.get("units", "mm"), self, current_extra=extra,
                              speed_factor=config.speed_factor(self.values))
        if not dlg.exec():
            return
        self.materials = dlg.materials
        try:
            path = material_lib.save_library(self.materials, self._materials_path())
            self.status(_("Material library saved to %s") % path)
        except OSError as e:
            self.status(_("Could not save the material library: %s") % e, error=True)
        self.layers_panel.set_materials([m.name for m in self.materials])

    def export_materials(self):
        name, _unused = QFileDialog.getSaveFileName(self, _("Export material library"),
                                                    os.path.join(os.path.expanduser("~"), "kerfly-materials.json"),
                                                    _("Material library") + " (*.json)")
        if not name:
            return
        if not name.lower().endswith(".json"):
            name += ".json"
        try:
            material_lib.export_library(self.materials, name)
        except OSError as e:
            QMessageBox.critical(self, _("Export material library"), str(e))
            return
        self.status(_("Material library exported to %s") % name)

    def import_materials(self):
        name, _unused = QFileDialog.getOpenFileName(self, _("Import material library"), os.path.expanduser("~"),
                                                    _("Material library") + " (*.json);;" + _("All files") + " (*)")
        if not name:
            return
        try:
            imported = material_lib.import_library(name)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, _("Import material library"),
                                 _("The file is not a Kerfly material library.") + "\n\n" + str(e))
            return
        self.materials, added, replaced = material_lib.merge_materials(self.materials, imported)
        try:
            material_lib.save_library(self.materials, self._materials_path())
        except OSError as e:
            self.status(_("Could not save the material library: %s") % e, error=True)
        self.layers_panel.set_materials([m.name for m in self.materials])
        QMessageBox.information(self, _("Import material library"),
                                _("Materials added: %d\nMaterials updated (same name): %d") % (added, replaced))

    def _update_layer_assignment(self):
        """Layer choice for each part of the selected element (in the bar above the bed)."""
        box = self.layer_assign_box
        grid = box.layout()
        while grid.count():
            w = grid.takeAt(0).widget()
            if w is not None:
                widgets.retire(w)          # hidden now, deleted by Qt later
        e = self.selected
        if e is not None and e.shape is not None:
            self._shape_layer_choice(e, grid)
            return
        kinds = [k for k in (RASTER, ENGRAVE, CUT, GCODE) if e is not None and part_present(e.design, k)]
        self.layer_assign_section.setVisible(bool(kinds))
        for row, kind in enumerate(kinds[:2] if len(kinds) <= 2 else kinds):
            combo = QComboBox()
            choices = [layer for layer in self.layers if layer.kind == kind]
            for layer in choices:
                combo.addItem(layer.name, layer.id)
                combo.setItemData(combo.count() - 1, QColor(layer.color), Qt.DecorationRole)
            current = layer_of(e, kind, self.layers)
            combo.setCurrentIndex(max(0, combo.findData(current.id if current else None)))
            combo.setFixedWidth(chars_width(combo, 14) + 48)
            combo.setToolTip(_(LAYER_KIND_NAMES[kind]))
            combo.currentIndexChanged.connect(lambda _i, c=combo, k=kind: self._assign_layer(k, c.currentData()))
            grid.addWidget(combo, 0, row)

    def _shape_layer_choice(self, e, grid):
        """A drawn shape: one list with every layer of the panel on the left. A
        layer of another kind changes what the laser does with the shape."""
        self.layer_assign_section.setVisible(True)
        combo = QComboBox()
        for layer in self.layers:
            if layer.kind == GCODE or (layer.kind == RASTER and not e.shape.closed):
                continue                                 # an open line has no area to engrave
            combo.addItem(layer.name, layer.id)
            combo.setItemData(combo.count() - 1, QColor(layer.color), Qt.DecorationRole)
        kind = OPERATION_KIND.get(e.shape.operation, CUT)
        current = layer_of(e, kind, self.layers)
        combo.setCurrentIndex(max(0, combo.findData(current.id if current else None)))
        combo.setFixedWidth(chars_width(combo, 14) + 48)
        combo.setToolTip(_("Layer of this shape: any layer from the panel on the left (cut, outline or "
                           "engrave)"))
        combo.currentIndexChanged.connect(lambda _i, c=combo: self._assign_shape_layer(c.currentData()))
        grid.addWidget(combo, 0, 0)
        from kerfly.core.shapes import has_pattern_fill
        if has_pattern_fill(e.shape) and e.shape.operation == "cut":
            # the pattern is a separate outline-engrave part: its own layer
            fill = QComboBox()
            for layer in self.layers:
                if layer.kind == ENGRAVE:
                    fill.addItem(layer.name, layer.id)
                    fill.setItemData(fill.count() - 1, QColor(layer.color), Qt.DecorationRole)
            current = layer_of(e, ENGRAVE, self.layers)
            fill.setCurrentIndex(max(0, fill.findData(current.id if current else None)))
            fill.setFixedWidth(chars_width(fill, 14) + 48)
            fill.setToolTip(_("Layer of the fill pattern (outline engraving)"))
            fill.currentIndexChanged.connect(lambda _i, c=fill: self._assign_layer(ENGRAVE, c.currentData()))
            grid.addWidget(fill, 0, 1)

    def _assign_shape_layer(self, layer_id):
        """Put the selected drawn shape on a layer, changing its operation when
        the layer is of another kind (cut / outline / engrave)."""
        e = self.selected
        layer = next((l for l in self.layers if l.id == layer_id), None)
        if e is None or e.shape is None or layer is None:
            return
        old_kind = OPERATION_KIND.get(e.shape.operation, CUT)
        if layer.kind == old_kind:
            self._assign_layer(layer.kind, layer_id)
            return
        spec = e.shape.copy()
        if layer.kind == CUT:
            spec.operation = "cut"
        elif layer.kind == ENGRAVE:
            spec.operation = "engrave"
        else:
            spec.operation = "fill"
        self._apply_shape(e, spec)                       # one undo step for the whole change
        e.layers.pop(old_kind, None)
        if layer_id != self._default_layer[layer.kind].id:
            e.layers[layer.kind] = layer_id
        self._layer_cache.clear()
        self._rebuild_layers_panel()
        self.refresh_preview()
        QTimer.singleShot(0, self, lambda: self._update_tool_options(force=True))

    def _assign_layer(self, kind, layer_id):
        e = self.selected
        if e is None or e.layers.get(kind, self._default_layer[kind].id) == layer_id:
            return
        self._checkpoint()
        if layer_id == self._default_layer[kind].id:
            e.layers.pop(kind, None)
        else:
            e.layers[kind] = layer_id
        self._layer_cache.clear()
        self._rebuild_layers_panel()
        self.refresh_preview()

    def _part_color(self, element, kind):
        layer = layer_of(element, kind, self.layers)
        return layer.color if layer is not None else None

    def _set_value(self, key, val):
        self.values[key] = val
        if key.endswith("_feed") or key.endswith("_passes") or key == "Gcde_passes":
            self._update_times()

    def _update_times(self):
        if not hasattr(self, "layers_panel"):
            return
        sim = self._open_simulation()
        if sim is not None:
            sim.design_changed()                     # it refreshes after a pause (docs/ui-mockups/Simulation)
        try:
            times = layer_times(self.elements, [l for l in self.layers if l.enabled],
                                self.job_settings(), self._layer_cache) if self.elements else {}
        except (ValueError, ZeroDivisionError):
            times = {}
        self.layers_panel.set_times(times, format_time)
        self._last_layer_times = times               # the Engrave / Outline / Cut buttons show their part
        if times:
            known = [t for t in times.values() if t is not None]
            unknown = any(t is None for t in times.values())
            if unknown and not known:
                text = "?"
            else:
                text = format_time(sum(known)) + (_(" + raster") if unknown else "")
            self.layers_panel.total_label.setText(_("Estimated total: <b>%s</b>") % text)
        else:
            self.layers_panel.total_label.setText("")

    def power_per_stage(self):
        """A power per layer: the K40's M3 board with power control, and every GRBL board (S)."""
        if self.is_grbl():
            return True
        return (self.values.get("board_name") == "LASER-M3"
                and is_true(self.values.get("show_power", "1")))

    def job_settings(self):
        s = config.job_settings_from_values(self.values, power_per_stage=self.power_per_stage())
        # the trace starts at the corner where the head is (K40 Whisperer: upper right first)
        return replace(s, trace_from_corner=True, trace_rectangle=is_true(self.values.get("trace_rect", "1")))

    def send_options(self):
        v = self.values
        return dict(pre_process_crc=is_true(v["pre_pr_crc"]), wait_for_laser=is_true(v["wait"]),
                    timeout_ms=float(v["t_timeout"]), n_timeouts=float(v["n_timeouts"]))

    def _design_has(self):
        has = {job.RASTER_ENG: False, job.VECTOR_ENG: False, job.VECTOR_CUT: False, job.GCODE_CUT: False}
        for e in self.elements:
            d = e.design
            has[job.RASTER_ENG] |= d.raster.image is not None
            has[job.VECTOR_ENG] |= bool(d.vector_engrave.ecoords)
            has[job.VECTOR_CUT] |= bool(d.vector_cut.ecoords)
            has[job.GCODE_CUT] |= bool(d.gcode.ecoords)
        return has

    def _update_power_visibility(self):
        """Layer rows for the loaded design; power column for M3 boards with power control."""
        grbl = self.values.get("machine") == "grbl"
        self.test_fire_row.setVisible(self.values.get("board_name") == "LASER-M3" and not grbl
                                      and is_true(self.values.get("show_test", "1")))
        for action in (self.act_save_egv, self.act_send_egv):   # EGV: a K40's data only
            action.setVisible(not grbl)
        self._rebuild_layers_panel()
        self._fit_panel_width()

    def _fit_window_height(self):
        """Grow the window so the whole job panel fits without scrolling
        (limited to the screen; the panel scrolls on small screens)."""
        scroll = self.panel_scroll
        panel = scroll.widget()
        chrome = self.height() - scroll.viewport().height()   # menus, toolbar, dock title, status bar
        needed = chrome + panel.sizeHint().height() + 2
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            frame = self.frameGeometry().height() - self.geometry().height()
            needed = min(needed, screen.height() - max(frame, 0))
        if self.height() < needed:
            self.resize(self.width(), needed)
            if screen is not None and self.frameGeometry().bottom() > screen.bottom():
                self.move(self.x(), max(screen.top(), screen.bottom() - self.frameGeometry().height()))

    # ---- window size and position, remembered between sessions ---------------
    @staticmethod
    def _window_settings():
        from PySide6.QtCore import QSettings
        from kerfly.core.materials import library_path
        return QSettings(os.path.join(os.path.dirname(library_path()), "window.ini"), QSettings.IniFormat)

    def _restore_window_geometry(self):
        """Last size and position; on the first start 85% of the screen, centred."""
        saved = self._window_settings().value("geometry")
        if saved is not None and self.restoreGeometry(saved):
            return True
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            w, h = int(screen.width() * 0.85), int(screen.height() * 0.85)
            self.resize(w, h)
            self.move(screen.x() + (screen.width() - w) // 2, screen.y() + (screen.height() - h) // 2)
        return False

    def _save_window_geometry(self):
        if not getattr(self, "remember_geometry", False):
            return                                  # tests and the self-test leave it alone
        try:
            settings = self._window_settings()
            settings.setValue("geometry", self.saveGeometry())
            settings.sync()
        except Exception:
            pass                                    # never block closing

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            # a narrow window must not squeeze the toolbar groups (labels cut to "Ot…rz"): what does not
            # fit goes behind the toolbar's » button; measured now, with the style sheet applied
            for group in getattr(self, "_ribbon_groups", []):
                group.setMinimumWidth(group.sizeHint().width())
            QTimer.singleShot(0, self, self._fit_panel_width)     # layout is final only once shown
            QTimer.singleShot(0, self, self._fit_window_height)

    def _update_unit_suffixes(self):
        units = self.values.get("units", "mm")
        speed = "mm/s" if units == "mm" else "in/min"
        for w, kind, _key, _sign in self._unit_widgets:
            w.setSuffix(" " + (units if kind == "len" else speed))
            refit_spin(w)
        self._fit_panel_width()

    def _fit_panel_width(self):
        """The left panel a little wider than its content needs (at least PANEL_WIDTH), never scrolling
        sideways."""
        scroll = getattr(self, "panel_scroll", None)
        if scroll is not None:
            for i in range(self.tabs.count()):
                self.tabs.widget(i).ensurePolished()     # a hidden tab gets its style only when shown
            scroll.setMinimumWidth(max(theme.PANEL_WIDTH, scroll.widget().minimumSizeHint().width()
                                       + scroll.verticalScrollBar().sizeHint().width() + theme.PANEL_ROOM))

    def _reload_spin_values(self):
        """Re-read unit-dependent fields after the units changed."""
        for w, kind, key, sign in self._unit_widgets:
            if key is None:
                continue
            w.blockSignals(True)
            try:
                w.setValue(max(w.minimum(), sign * float(self.values[key])))
            except (KeyError, ValueError):
                pass
            w.blockSignals(False)

    def _update_laser_state(self):
        # the state: a dot (green: connected) and its words, in the Laser tab and in the status bar
        connected = bool(self.laser.connected)
        if connected:
            board = "GRBL" if self.is_grbl() else self.values.get("board_name")
            self.laser_label.setText(_("Connected (%s)") % board)
            self.btn_connect.setToolTip(_("Connected. Click to connect again (re-initialize)."))
        else:
            self.laser_label.setText(_("Not connected"))
            self.btn_connect.setToolTip(_("Connect to the laser") + " (Ctrl+I)")
        self.btn_connect.setIcon(icons.tabler("plug-connected", theme.token("ok") if connected else None))
        for dot in (self.laser_dot, getattr(self, "status_laser_dot", None)):
            if dot is not None:
                widgets.set_dot(dot, "ok" if connected else "")
        if getattr(self, "status_laser", None) is not None:
            self.status_laser.setText(_("Laser: connected") if connected else _("Laser: not connected"))
        x, y = self.head
        scale = 25.4 if self.values.get("units") == "mm" else 1.0
        self.head_label.setText("X %s  Y %s %s" % (_num(x * scale), _num(-y * scale), self.values.get("units")))

    def set_busy(self, busy):
        for w in [self.btn_start, self.btn_trace, self.btn_connect, self.btn_home, self.btn_unlock,
                  self.btn_goto,
                  self.btn_test_fire, self.btn_calc_time, self.selection_box, self.profile_box] + self.corner_buttons:
            w.setEnabled(not busy)
        for a in [self.act_new, self.act_open, self.act_reload, self.act_save_egv, self.act_send_egv,
                  self.act_connect, self.act_release, self.act_home, self.act_unlock,
                  self.act_settings, self.act_profiles, self.act_goto, self.act_calc_time, self.act_add, self.act_delete,
                  self.act_rot_left, self.act_rot_right, self.act_mirror_h, self.act_mirror_v,
                  self.act_group, self.act_ungroup, self.act_distribute_h, self.act_distribute_v, self.act_place_head,
                  self.act_follow_head, self.act_undo] + list(self.act_order.values()) + [
                  self.act_redo, self.act_duplicate, self.act_center] + list(self.act_corners.values()) \
                + list(self.act_align.values()) + list(self.act_boolean.values()) + [self.act_offset] \
                + [self.act_cut, self.act_paste, self.act_paste_in_place]:
            a.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)
        self.act_stop.setEnabled(busy)
        for a in self.tool_actions.values():
            a.setEnabled(not busy)
        self.tool_options.setEnabled(not busy)
        self.progress.setValue(0)
        self.progress.setVisible(busy)
        self.busy_indicator.setVisible(busy)
        self._update_bed_check()

    def status(self, message, error=False):
        m = _PERCENT_RE.search(message)
        if m and hasattr(self, "progress"):            # "Sending Data to Laser = 42.0%" etc.
            self.progress.setValue(max(0, min(100, int(float(m.group(1))))))
        # the log gets each message once in a row: the laser library repeats some
        # (e.g. "Waiting for the laser to finish." while polling), which filled the log
        if message != getattr(self, "_last_logged_status", None):
            if error:
                diag_log.warning("status: %s", message)
                self._last_logged_status = message
            elif not message.endswith("%") and "%: " not in message:
                diag_log.info("status: %s", message)     # progress percentages are left out
                self._last_logged_status = message
        bar = self.statusBar()
        if bool(bar.property("error")) != bool(error):     # red text for an error (theme.py's style sheet)
            bar.setProperty("error", bool(error))
            bar.style().unpolish(bar)
            bar.style().polish(bar)
        bar.showMessage(tr_message(message))

    def refresh_preview(self, fit=False):
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        if self.selected not in self.elements:
            self.selected = None
        self.preview.show_layout(self.elements, self.selected, settings, self.values, self.head, fit=fit,
                                 grid_mm=self._grid_mm(), part_color=self._part_color)
        self._update_element_list()
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))
        self._update_laser_state()
        self._update_selection_panel()
        # the options bar and the Layer lists follow too (a deleted or undone element left them showing it)
        self._update_layer_assignment()
        self._update_tool_options()
        self._update_times()
        self._update_bed_check()
        if hasattr(self, "status_bed"):
            self._show_view_state()                  # the bed's size may have changed (settings, a profile)

    # ------------------------------------------------------------ design files
    def new_project(self):
        """File → New project: an empty bed, the layers back to the default ones
        (with the speeds and powers last used), nothing to undo."""
        if self.worker is not None or not self._confirm_discard():
            return
        self._close_simulation()
        self.elements = []
        self.group_names = {}
        self.selected = None
        self._default_layer = {}
        self._init_layers()
        self._undo.clear()
        self._redo.clear()
        self._compiled = None
        self._layer_cache.clear()
        self.project_file = ""
        self._set_dirty(False)
        self._rebuild_layers_panel()
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview(fit=True)
        self.status(_("New project"))

    def open_design(self, add=False):
        start = os.path.dirname(self.design_file or self.values.get("designfile", "")) or os.path.expanduser("~")
        title = _("Add design") if add else _("Open design")
        name, _unused = QFileDialog.getOpenFileName(self, title, start, design_filters())
        if name:
            self.load_design(name, add=add)

    def add_design(self):
        self.open_design(add=True)

    def reload_design(self):
        """Reload every element's file, keeping its placement."""
        if not self.elements:
            self.open_design()
            return
        self._checkpoint()
        for e in list(self.elements):
            if e.shape is not None:
                e.design = build_design(e.shape)
                continue
            design = self._load_file(e.source_file, e.load_options)
            if design is None:
                return
            e.design = design
        self._layout_changed()
        self.status(_("Reloaded"))

    # ------------------------------------------------------------ projects
    def _set_dirty(self, dirty):
        self._dirty = dirty
        self._update_title()

    def _update_title(self):
        name = os.path.basename(self.project_file) if self.project_file else _("Untitled")
        self.setWindowTitle("%s%s \u2013 Kerfly %s" % ("*" if self._dirty else "", name, __version__))

    def _confirm_discard(self):
        """Ask to save unsaved changes. Returns False if the user cancels."""
        if not self._dirty or not self.elements:
            return True
        answer = widgets.ask(
            self, _("Unsaved changes"), _("Save the changes to the project first?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save,
            names={QMessageBox.Discard: _("Don't save")}, primary=QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_project()
        return True

    def save_project(self):
        if not self.project_file:
            return self.save_project_as()
        return self._write_project(self.project_file)

    def save_project_as(self):
        start = self.project_file or os.path.join(
            os.path.dirname(self.design_file) or os.path.expanduser("~"),
            (os.path.splitext(os.path.basename(self.design_file))[0] or _("project")) + project_io.EXTENSION)
        name, _unused = QFileDialog.getSaveFileName(self, _("Save project"), start,
                                                    _("Kerfly projects") + " (*.kerfly)")
        if not name:
            return False
        if not name.lower().endswith(project_io.EXTENSION):
            name += project_io.EXTENSION
        return self._write_project(name)

    def _write_project(self, path):
        try:
            project_io.save_project(path, self.elements, self.layers, group_names=self.group_names)
        except (OSError, project_io.ProjectError) as e:
            QMessageBox.critical(self, _("Could not save the project"), str(e))
            return False
        self.project_file = path
        self._set_dirty(False)
        self.status(_("Project saved: %s") % path)
        return True

    def open_project(self, path):
        if self.worker is not None or not self._confirm_discard():
            return
        self._close_simulation()
        try:
            data, _folder = project_io.read_project(path)
        except project_io.ProjectError as e:
            QMessageBox.critical(self, _("Could not open the project"), str(e))
            return
        layers, by_id = project_io.layers_from_data(data)
        for kind in KINDS:                       # every kind needs a default layer
            if not any(layer.kind == kind for layer in layers):
                from kerfly.core.layers import DEFAULT_COLORS
                layers.append(Layer(kind, name=_(LAYER_KIND_NAMES[kind]), color=DEFAULT_COLORS[kind]))
        elements = []
        for item in data.get("elements", []):
            shape = project_io.shape_from_item(item)
            if shape is not None:
                design = build_design(shape)
                source, options = "", {}
            else:
                options = dict(item.get("load_options") or {})
                source = item["path"]
                design = self._load_file(source, options)
                if design is None:
                    return
            e = Element(design, name=item.get("name", ""), source_file=source, load_options=options,
                        origin=str(item.get("origin") or item.get("original_path") or ""),
                        shape=shape, x=float(item["x"]), y=float(item["y"]),
                        scale_x=float(item.get("scale_x", 1)), scale_y=float(item.get("scale_y", 1)),
                        rotation=float(item.get("rotation", 0)), visible=bool(item.get("visible", True)),
                        group=str(item.get("group", "") or ""))
            for kind, saved_id in (item.get("layers") or {}).items():
                if saved_id in by_id:
                    e.layers[kind] = by_id[saved_id].id
            elements.append(e)
        self.layers = layers
        self._default_layer = {}
        for layer in layers:
            self._default_layer.setdefault(layer.kind, layer)
        for layer in self._default_layer.values():
            self._layer_to_values(layer)
        self.elements = elements
        self.group_names = {str(k): str(v) for k, v in (data.get("groups") or {}).items()}
        self.selected = None
        self._undo.clear()
        self._redo.clear()
        self._compiled = None
        self._layer_cache.clear()
        self.project_file = path
        self.design_file = path
        self._set_dirty(False)
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview(fit=True)
        self.status(_("Project opened: %s") % path)

    def _ask_dxf_units(self):
        unit, ok = QInputDialog.getItem(self, _("DXF units"),
                                        _("The DXF file does not say which units it uses.\nUnits:"),
                                        loaders.DXF_UNITS, loaders.DXF_UNITS.index("Millimeters"),
                                        False)
        return unit if ok else None

    def _ask_svg_scale(self, svg_size, viewbox, inkscape_version):
        q = loaders.SvgScale(svg_size, viewbox, inkscape_version)
        w, h = q.size_mm(q.default_pxpi)
        pxpi, ok = QInputDialog.getDouble(
            self, _("SVG import scale"),
            _("The SVG file does not define its physical size.\n"
            "Pixels per inch (Inkscape 0.92+: 96, older Inkscape: 90, Illustrator: 72).\n"
            "At %g px/in the design is %.1f x %.1f mm.") % (q.default_pxpi, w, h),
            q.default_pxpi, 1.0, 10000.0, 2)
        return q.result(pxpi) if ok else None

    def _ask_image_dpi(self, filename):
        """Ask for the physical size of a bitmap; returns its dpi or None if cancelled."""
        try:
            width, height, file_dpi = loaders.read_image_info(filename)
        except Exception as e:
            QMessageBox.critical(self, _("Could not open design"), tr_message(str(e)))
            return None
        dlg = ImageSizeDialog(width, height, file_dpi, self.values.get("units", "mm"), self)
        if not dlg.exec():
            return None
        return dlg.result_dpi()

    def _load_file(self, filename, options):
        """Load a file into a new Design. options may hold {"dpi": ...} for images.
        Returns the design, or None if loading failed or was cancelled."""
        ext = os.path.splitext(filename)[1].lower()
        design = Design()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status(_("Opening %s") % filename)
        QApplication.processEvents()

        def progress(msg):
            self.status(msg)
            QApplication.processEvents()
        reduced = is_true(self.values.get("reduced_mem", "0"))

        def ask_pxpi(size, viewbox, version):        # answer remembered in the options
            if "svg_scale" in options:
                pxpi, vb = options["svg_scale"]
                return pxpi, list(vb)
            answer = self._ask_svg_scale(size, viewbox, version)
            if answer is not None:
                options["svg_scale"] = [answer[0], list(answer[1])]
            return answer

        def ask_units():
            if "dxf_units" not in options:
                unit = self._ask_dxf_units()
                if unit is None:
                    return None
                options["dxf_units"] = unit
            return options["dxf_units"]
        try:
            if ext == ".svg":
                warnings = loaders.load_svg(
                    filename, design,
                    inkscape_path=self.values.get("inkscape_path", ""),
                    inkscape_timeout_s=float(self.values.get("ink_timeout", 3)) * 60.0,
                    reduced_memory=reduced, ask_pxpi=ask_pxpi, progress=progress,
                    svg_renderer=render_svg, use_inkscape=is_true(self.values.get("use_inkscape", "1")))
            elif ext == ".dxf":
                warnings = loaders.load_dxf(filename, design, ask_units=ask_units)
            elif ext in loaders.IMAGE_EXTENSIONS:
                warnings = loaders.load_image(filename, design, options["dpi"], reduced_memory=reduced)
            else:
                warnings = loaders.load_gcode(filename, design)
        except loaders.LoadCancelled:
            QApplication.restoreOverrideCursor()
            self.status(_("Loading cancelled"))
            return None
        except Exception as e:
            QApplication.restoreOverrideCursor()
            from kerfly.core import diag
            diag.log.warning("opening %s failed: %s", filename, e, exc_info=True)   # the reason, for reports
            self.status(_("Could not open %s") % os.path.basename(filename), error=True)
            QMessageBox.critical(self, _("Could not open design"), tr_message(str(e)))
            return None
        QApplication.restoreOverrideCursor()
        for w in warnings:
            QMessageBox.warning(self, _("Design import"), tr_message(w))
        if options.get("raster_only"):                   # its lines were broken apart into shapes
            from kerfly.core.explode import raster_only
            design = raster_only(design)
        return design

    def load_design(self, filename, add=False):
        """Open a file as a new element at the laser head; replaces all elements unless add.
        A .kerfly file opens as a project."""
        if filename.lower().endswith(project_io.EXTENSION):
            self.open_project(filename)
            return
        if not add and not self._confirm_discard():
            return
        if not add:
            self._close_simulation()
        options = {}
        if os.path.splitext(filename)[1].lower() in loaders.IMAGE_EXTENSIONS:
            dpi = self._ask_image_dpi(filename)
            if dpi is None:
                self.status(_("Loading cancelled"))
                return
            options["dpi"] = dpi
        design = self._load_file(filename, options)
        if design is None:
            return
        self._checkpoint()
        is_gcode = bool(design.gcode.ecoords)
        if not add or is_gcode or any(e.design.gcode.ecoords for e in self.elements):
            self.elements = []         # G-code files are not combined with other designs
        element = Element(design, name=os.path.basename(filename), source_file=filename,
                          load_options=options)
        element.x, element.y = self.head
        self._keep_on_bed(element)
        self.elements.append(element)
        self.selected = element
        self.design_file = filename
        self.values["designfile"] = filename
        self._compiled = None
        self._update_design_label()
        self._update_power_visibility()
        self.refresh_preview(fit=not add)
        self.status(_("Opened %s") % filename)
        if not self._layout_fits_bed():
            self.status(_("The design does not fit on the laser bed at this position."), error=True)

    def _update_design_label(self):
        if not self.elements:
            self.design_label.setText(_("No design loaded"))
            self.design_label.setToolTip("")
            widgets.set_role(self.design_label, "hint")
            return
        parts = []
        has = self._design_has()
        for op, text in ((job.RASTER_ENG, _("raster")), (job.VECTOR_ENG, _("vector engrave")),
                         (job.VECTOR_CUT, _("vector cut")), (job.GCODE_CUT, _("g-code"))):
            if has[op]:
                parts.append(text)
        xmin = min(e.bounds[0] for e in self.elements)
        xmax = max(e.bounds[1] for e in self.elements)
        ymin = min(e.bounds[2] for e in self.elements)
        ymax = max(e.bounds[3] for e in self.elements)
        # one line in the Elements header: how many, how large; what they hold in its tooltip; red when the
        # design does not fit on the bed
        title = self.elements[0].name if len(self.elements) == 1 else \
            ngettext("%d element", "%d elements", len(self.elements)) % len(self.elements)
        size = _("%s \u00d7 %s mm") % (_num((xmax - xmin) * 25.4), _num((ymax - ymin) * 25.4))
        fits = self._layout_fits_bed()
        text = "%d \u00b7 %s" % (len(self.elements), size)
        if not fits:
            text += " \u00b7 " + _("Outside the laser bed!")
        self.design_label.setText(text)
        self.design_label.setToolTip("%s\n%s\n%s" % (title, size, ", ".join(parts) or _("empty")))
        widgets.set_role(self.design_label, "hint" if fits else "error")

    # ------------------------------------------------------------ settings
    def edit_settings(self):
        dlg = SettingsDialog(self.values, self)
        if not dlg.exec():
            return
        new, changed = dlg.result_values()
        if not changed:
            return
        self._apply_settings(new, changed)
        from kerfly.core import profiles as profiles_core
        if changed & set(profiles_core.MACHINE_KEYS):
            # a machine setting: kept in the profile of the laser in use at once
            self._store_profile()
            self.status(_("Settings changed; the laser \"%s\" keeps them") % self.profiles.current)
        else:
            self.status(_("Settings changed (use File → Save settings as default to keep them)"))

    def _materials_path(self):
        """The material library of the laser in use: its own, or the one it shares."""
        return material_lib.library_path(self.profiles.library_owner(self.profiles.current) or None)

    def _load_materials(self):
        """The material library of the laser in use (the examples for a laser without one yet)."""
        try:
            self.materials = material_lib.load_library(self._materials_path())
        except (OSError, ValueError) as e:
            self.materials = material_lib.example_materials()
            diag_log.warning("material library not read: %s", e)
        if hasattr(self, "layers_panel"):
            self.layers_panel.set_materials([m.name for m in self.materials])

    def _store_profile(self):
        from kerfly.core import profiles as profiles_core
        settings = profiles_core.from_values(self.values)
        if not settings.get("laser_id"):                  # never lose the id of its material library
            settings["laser_id"] = self.profiles.get(self.profiles.current).get("laser_id", "")
        self.profiles.set(self.profiles.current, settings)
        try:
            profiles_core.save(self.profiles)
        except OSError as e:
            self.status(_("Could not save the lasers: %s") % e, error=True)

    def _refresh_profile_box(self):
        box = getattr(self, "profile_box", None)
        if box is None:
            return
        box.blockSignals(True)
        box.clear()
        for name in self.profiles.names():
            box.addItem(icons.tabler("laser"), name)
        box.setCurrentIndex(max(0, box.findText(self.profiles.current)))
        box.blockSignals(False)

    def switch_profile(self, name):
        """Work with another laser: its settings go into the window. False while a job runs."""
        from kerfly.core import profiles as profiles_core
        if name == self.profiles.current:
            return True
        if self.worker is not None or getattr(self, "_before_job_process", None) is not None:
            self.status(_("Wait until the job ends before choosing another laser."), error=True)
            self._refresh_profile_box()
            return False
        new = profiles_core.to_values(self.values, self.profiles.get(name))
        changed = {k for k in new if str(new[k]) != str(self.values.get(k, ""))}
        self.profiles.current = name
        try:
            profiles_core.save(self.profiles)
        except OSError as e:
            self.status(_("Could not save the lasers: %s") % e, error=True)
        if changed:
            self._apply_settings(new, changed)
        self._load_materials()                       # this laser's material library
        released = False
        if self.laser.connected and not self.is_grbl() and "usb_port" in changed and self.values.get("usb_port") \
                and self.values.get("usb_port") != self.laser.port_key:
            # another machine on another USB port: the next Connect opens it
            self.laser.release()
            self._update_laser_state()
            released = True
        self._refresh_profile_box()
        diag_log.info("laser profile %s: board %s, bed %s x %s", name, self.values.get("board_name"),
                      self.values.get("LaserXsize"), self.values.get("LaserYsize"))
        self.status(_("Laser: %s") % name + (" — " + _("connect to it with the plug button") if released else ""))
        return True

    def manage_profiles(self):
        from kerfly.gui.profiles_dialog import ProfilesDialog
        ProfilesDialog(self).exec()
        self._refresh_profile_box()

    def _make_laser(self):
        """The controller of this machine: a K40 (USB) or a GRBL board (serial port)."""
        if self.values.get("machine") == "grbl":
            laser = GrblController()
            self._grbl_speeds(laser)
            return laser
        return LaserController()

    def is_grbl(self):
        return isinstance(self.laser, GrblController)

    def _machine_changed(self, changed):
        """Another kind of machine, or another serial port: the next Connect opens it."""
        want_grbl = self.values.get("machine") == "grbl"
        if want_grbl != self.is_grbl() or (want_grbl and changed & {"grbl_port", "grbl_baud"}):
            if self.laser.connected:
                try:
                    self.laser.release()
                except Exception:
                    pass
            self.laser = self._make_laser()
            self._update_laser_state()
        elif want_grbl and "grbl_jog" in changed:
            self._grbl_speeds(self.laser)

    def _grbl_speeds(self, laser):
        """The laser's jog speed into a GRBL controller (the homing speed is the board's own, $25: Kerfly
        does not change it, user 2026-11-20)."""
        try:
            laser.jog_feed = float(self.values.get("grbl_jog", 3000) or 3000)
        except ValueError:
            pass

    def _home_head(self):
        """Where the head is after homing (bed inches: x from home for a K40, from the left for GRBL; y <= 0
        from the top): the laser's home corner."""
        corner = self.home_corner()
        bed_w, bed_h = config.bed_size_inches(self.values)
        return (bed_w if corner[1] == "R" and self.is_grbl() else 0.0, -bed_h if corner[0] == "L" else 0.0)

    def _apply_settings(self, new, changed):
        """New settings into the window (Settings dialog, another laser)."""
        if "units" in changed:
            old = dict(new)
            old["units"] = self.values["units"]
            new = config.convert_units(old, new["units"])
        self.values.clear()
        self.values.update(new)
        self._machine_changed(changed)
        if changed & {"materials_shared", "materials_from"}:
            self._load_materials()                   # another material library
        self._reload_spin_values()
        self._update_unit_suffixes()
        self._update_power_visibility()
        from kerfly.gui import viewstate
        if changed & set(viewstate.KEYS):
            self._remember_view()                # e.g. the language: kept for the next start at once
        if "language" in changed:
            QMessageBox.information(self, _("Language"),
                                    _("The new language will be used after restarting Kerfly."))
        if "theme" in changed:
            QMessageBox.information(self, _("Theme"), _("The new theme will be used after restarting Kerfly."))
        if "units" in changed:
            factor = (60.0 / 25.4) if self.values.get("units") == "in" else (25.4 / 60.0)
            for layer in self.layers:
                if self._default_layer.get(layer.kind) is not layer:
                    layer.speed = round(layer.speed * factor, 1)
        self._layers_from_values()
        if changed & {"grid_mm", "snap_objects", "follow_head"}:
            self._sync_view_actions()
        if changed & {"HomeUR", "home_lower", "grbl_home", "machine"} and not self.laser.connected:
            self.head = self._home_head()            # another home corner: the head shown there (as after Home)
            if self.follow_head():
                self._design_to_head(checkpoint=False)
        if "kind_buttons" in changed:
            self.kind_row.setVisible(is_true(self.values.get("kind_buttons", "0")))
        if changed & RASTER_KEYS:
            for e in self.elements:
                e.design.raster.reset_path()
            self._compiled = None
            self._layer_cache.clear()
        if changed & RELOAD_KEYS and self.elements:
            self.reload_design()
        self.refresh_preview()

    def save_settings(self):
        path = config.user_config_path()
        try:
            config.write_settings_file(path, self.values, "0.71 (Kerfly %s)" % __version__)
        except OSError as e:
            self.status(_("Could not save settings: %s") % e, error=True)
            return
        self.status(_("Settings saved to %s") % path)

    # ------------------------------------------------------------ laser
    def _laser_call(self, func, ok_message):
        if not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return False
        try:
            func()
        except Exception as e:
            self.status(str(e), error=True)
            return False
        self.status(ok_message)
        return True

    def _choose_laser(self, ports):
        """Several K40 plugged in, none on this laser's port: ask which one (None: cancelled)."""
        from kerfly.gui.usb_port_dialog import ChooseLaserDialog
        QApplication.restoreOverrideCursor()
        dlg = ChooseLaserDialog(ports, self.laser, self.profiles.current, self)
        chosen = dlg.chosen() if dlg.exec() else None
        self._port_chosen = chosen is not None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        return chosen

    def connect_laser(self):
        if self.is_grbl():
            self._connect_grbl()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._port_chosen = False
        try:
            self.laser.connect(init_home=is_true(self.values.get("init_home", "1")),
                               port=self.values.get("usb_port", ""), choose=self._choose_laser)
            self.head = self._home_head()
            self.status(_("Laser initialized"))
            if self._port_chosen and self.laser.port_key:
                # remembered in this laser's profile: next time no question
                self.values["usb_port"] = self.laser.port_key
                self._store_profile()
                self.status(_("Laser initialized; \"%s\" remembers its USB port (%s)")
                            % (self.profiles.current, self.laser.port_key))
        except LaserError as e:
            self.status(str(e), error=True)
            from kerfly.core import udev
            if udev.applies() and udev.permission_problem(str(e)):
                QApplication.restoreOverrideCursor()
                QTimer.singleShot(0, self, lambda: self.allow_usb_access(after_error=True))
        except Exception as e:
            self.status(_("Unknown USB error: %s") % e, error=True)
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_preview()

    def _connect_grbl(self):
        """Connect a GRBL board (serial port); with homing on and Settings → Machine → Home when
        initializing, it homes."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            home = is_true(self.values.get("init_home", "1")) and self.laser is not None
            self.laser.connect(init_home=home, port=self.values.get("grbl_port", ""),
                               baud=self.values.get("grbl_baud", "115200") or "115200")
            homed = home and self.laser.settings.get("$22", "0") not in ("0", "")
            # homed or not, the head is taken to be at the machine's home corner (a board without limit
            # switches counts from where the head was when it was switched on: put it in that corner)
            self.head = self._home_head()
            diag_log.info("grbl: %s on %s, homed %s, $$ %s", self.laser.version, self.laser.port_key, homed,
                          self.laser.settings)
            if self.laser.settings.get("$32", "1") == "0":
                self.status(_("%(version)s on %(port)s. Laser mode is off ($32=0): the head stops at every "
                              "corner; switch it on with $32=1 in the machine's settings.")
                            % {"version": self.laser.version, "port": self.laser.port_key}, error=True)
            else:
                self.status(_("%(version)s on %(port)s: connected%(homed)s") % {
                    "version": self.laser.version, "port": self.laser.port_key,
                    "homed": _(", homed") if homed else _("; Kerfly takes the head to be in the home corner "
                                                          "(Settings → Machine)")})
        except LaserError as e:
            self.status(str(e), error=True)
        except Exception as e:
            self.status(_("Unknown error: %s") % e, error=True)
        finally:
            QApplication.restoreOverrideCursor()
        self._update_laser_state()
        self.refresh_preview()

    def install_desktop_entry(self):
        """Linux AppImage: menu entry and .kerfly file type in the user's own folders."""
        from kerfly.gui import desktop_entry
        try:
            desktop_entry.install()
        except Exception as e:
            QMessageBox.warning(self, _("Applications menu"), _("Kerfly could not be added: %s") % e)
            return
        QMessageBox.information(
            self, _("Applications menu"),
            _("Kerfly is in the applications menu, and .kerfly projects open in Kerfly with a double click.\n\n"
              "After moving the AppImage file, choose this again. A newer version updates the entry "
              "by itself when it starts."))

    def allow_usb_access(self, after_error=False):
        """Linux: install the udev rule for the K40 board through pkexec (one password prompt)."""
        from kerfly.core import udev
        if udev.installed() and not after_error:
            QMessageBox.information(self, _("USB access"),
                                    _("The rule for the laser's USB port is already installed. If Kerfly still "
                                      "cannot connect, unplug the laser's USB cable and plug it in again."))
            return
        text = _("The laser was found, but this user may not use its USB port.") + "\n\n" if after_error else ""
        answer = widgets.ask(
            self, _("USB access"),
            text + _("Kerfly can add a rule to the system so that the laser's USB port can be used without "
                     "root. The system asks for the administrator password once. Add the rule now?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes, names={QMessageBox.Yes: _("Add the rule")})
        if answer != QMessageBox.Yes:
            return
        ok, why = udev.install()
        if ok:
            QMessageBox.information(self, _("USB access"),
                                    _("Done. Unplug the laser's USB cable, plug it in again, then connect."))
            self.status(_("USB rule installed: unplug the laser and plug it in again."))
        elif why == "cancelled":
            self.status(_("USB rule not installed (the password window was closed)."), error=True)
        else:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(_("USB access"))
            box.setText(_("The rule could not be added here (%s). Type these commands in a terminal, then unplug "
                          "the laser and plug it in again:") % why)
            box.setInformativeText("\n".join(udev.manual_commands()))
            box.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.exec()

    def release_laser(self):
        try:
            self.laser.release()
            self.status(_("USB released"))
        except Exception as e:
            self.status(str(e), error=True)
        self._update_laser_state()

    def home(self):
        if self.laser.connected and not self._laser_call(self.laser.home, _("Homed")):
            return
        self.head = self._home_head()
        if self.follow_head():
            self._design_to_head(checkpoint=False)
        self.refresh_preview()

    def unlock(self):
        self._laser_call(self.laser.unlock, _("Rail unlocked"))

    def unfreeze(self):
        self._laser_call(self.laser.unfreeze, _("Unfreeze complete"))

    def jog(self, dirx, diry):
        """Move by one jog step in the given direction (+y = up)."""
        try:
            step = float(self.values["jog_step"])
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self.move_by(dirx * step, diry * step)

    def move_by(self, dx_units, dy_units):
        """Move the laser head by (dx, dy) in the current units (+y = up, +x = right on screen)."""
        if self.worker is not None:
            return
        try:
            settings = self.job_settings()
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        f = 1.0 if self.values.get("units") == "in" else 1 / 25.4
        dx = round(dx_units * f, 3)
        dy = round(dy_units * f, 3)
        if settings.home_upper_right:
            dx = -dx
        if not (self.follow_head() and self.elements):
            x, y = clamp_head_position(self.head[0], self.head[1], dx, dy, bed_w, bed_h)
            self.move_head_to(x, y)
            return
        # the design moves along, the head keeping its place on it (after a corner button the head may be on
        # another corner of the design than its origin): both stay on the bed, as in K40 Whisperer
        b = self.design.get_bounds(settings.rotate)
        ox, oy = self.origin
        offset = (round(self.head[0] - ox, 3), round(self.head[1] - oy, 3))
        nx, ny = clamp_head_position(ox, oy, dx, dy, bed_w, bed_h, b[1] - b[0], b[3] - b[2], offset)
        if self.move_head_to(nx + offset[0], ny + offset[1], follow=False):
            self._shift_design(nx - ox, ny - oy)

    def move_head_to(self, x, y, follow=True):
        """Move the laser head to a bed position (inches, y <= 0). Returns True on success.
        With "Design follows the head" on, the design moves along (follow=False: it stays,
        e.g. for the corner buttons)."""
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return False
        dx = round((x - self.head[0]) * 1000.0)
        dy = round((y - self.head[1]) * 1000.0)
        if self.laser.connected and (dx or dy):
            try:
                self.laser.rapid_move(dx, dy, settings, self.send_options())
            except Exception as e:
                self.status(_("Rapid move failed: %s") % e, error=True)
                return False
        self.head = (self.head[0] + dx / 1000.0, self.head[1] + dy / 1000.0)
        if follow and self.follow_head():
            self._design_to_head(checkpoint=False)
        self.refresh_preview()
        return True

    def move_to_corner(self, corner):
        """Move the head to a corner or the centre of the design (the design stays)."""
        if self.worker is not None or not self.elements:
            return
        try:
            settings = self.job_settings()
            bed_w, bed_h = config.bed_size_inches(self.values)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        bounds = self.design.get_bounds(settings.rotate)
        ox, oy = self.origin
        offset = corner_offset(corner, bounds, settings.home_upper_right, (ox, oy), bed_w, bed_h)
        if offset is None:
            self.status(_("That corner of the design is outside the laser bed."), error=True)
            return
        x, y = clamp_head_position(ox, oy, offset[0] / 1000.0, offset[1] / 1000.0, bed_w, bed_h)
        self.move_head_to(x, y, follow=False)              # the corner buttons only show the corner

    def goto_position(self):
        """Home, then move to the X/Y set in the panel (distance from home, Y downwards)."""
        if self.worker is not None:
            return
        x, y = self.goto_x.value(), self.goto_y.value()
        if self.laser.connected and not self._laser_call(self.laser.home, _("Homed")):
            return
        self.head = self._home_head()
        # from home: Y down from an upper corner, up from a lower one; X left from a GRBL laser's right corner
        # (a K40's x runs from home anyway)
        self.move_by(-x if self.head[0] > 0 else x, y if self.head[1] < 0 else -y)

    def test_fire(self):
        if not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return
        try:
            ms = int(float(self.values["test_time"]))
            if ms > 1000:
                ms = 0
            fraction = float(self.values["test_power"])
            if fraction > 1:
                fraction = 0
            power = fraction * float(self.values["max_power"])
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self._laser_call(lambda: self.laser.test_fire(power, ms),
                         _("Test fire: %.0f%% for %d ms") % (power, ms))

    def calculate_raster_time(self):
        if self.worker is not None or not any(part_present(e.design, RASTER) for e in self.elements):
            return
        try:
            settings = self.job_settings()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        self._run_worker(RasterLayersWorker(self.elements, self.layers, settings, self._layer_cache,
                                            parent=self), _("Preparing raster\u2026"))

    def send_egv_file(self):
        if self.worker is not None:
            return
        if self.is_grbl():
            self.status(_("EGV files are for K40 lasers; a GRBL laser runs G-code (File → Save G-code)."),
                        error=True)
            return
        if not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return
        start = os.path.dirname(self.design_file) or os.path.expanduser("~")
        name, _unused = QFileDialog.getOpenFileName(self, _("Send EGV file"), start,
                                              _("EGV files (*.egv *.EGV);;All files (*)"))
        if not name:
            return
        try:
            egv = egvfile.read_egv_file(name)
            settings = self.job_settings()
            send_options = self.send_options()
        except (OSError, ValueError) as e:
            self.status(_("Could not read %s: %s") % (os.path.basename(name), e), error=True)
            return
        passes = 1
        if not egv.has_end_position:
            passes, ok = QInputDialog.getInt(self, _("Send EGV file"), _("Number of passes:"), 1, 1, 100)
            if not ok:
                return
        # the loaded design is not what is being cut: clear it, as K40 Whisperer does
        self._checkpoint()
        self.elements = []
        self.selected = None
        self.design_file = name
        self._layout_changed()
        self._run_worker(EgvSendWorker(egv, passes, self.laser, settings, send_options, parent=self),
                         _("Sending %s…") % os.path.basename(name))

    # ------------------------------------------------------------ jobs
    def start_job(self, output_file=None, trace=False, kinds=None, _program_done=False):
        """Run the job (trace: only the boundary). kinds: only the ticked layers of
        these kinds (Engrave / Outline / Cut only)."""
        if self.worker is not None or getattr(self, "_before_job_process", None) is not None:
            return
        wanted = [l for l in self.layers if kinds is None or l.kind in kinds]
        if not any(l.enabled and self._layer_has_data(l) for l in wanted) and not (trace and self.elements):
            self.status(_("Nothing to do: load a design and select at least one operation."), error=True)
            return
        if not self._layout_fits_bed():
            self.status(_("The design does not fit on the laser bed at this position."), error=True)
            return
        if output_file is None and not self.laser.connected:
            self.status(_("Laser is not initialized."), error=True)
            return
        try:
            settings = self.job_settings()
            send_options = self.send_options()
        except ValueError as e:
            self.status(str(e), error=True)
            return
        program = str(self.values.get("pre_batch_path", "")).strip()
        if output_file is None and not trace and not _program_done and program \
                and is_true(self.values.get("pre_exec", "0")):
            # the program before the job (the exhaust on, ...): the job waits until it ends
            self._run_before_job_program(program, lambda: self.start_job(output_file, trace, kinds,
                                                                          _program_done=True))
            return
        if output_file is None and self.head != self.origin:
            # the job starts where the head is: first move it to the design
            if not self.move_head_to(*self.origin, follow=False):
                return
        diag_log.info("job: %s to %s; board %s; origin %s; elements %s; layers %s",
                      "trace" if trace else "start", output_file or "laser", self.values.get("board_name"),
                      tuple(round(v, 4) for v in self.origin),
                      [(e.name, round(e.x, 3), round(e.y, 3), round(e.rotation, 1)) for e in self.elements
                       if e.visible],
                      [(l.name, l.kind, l.speed, l.passes, round(l.power, 2)) for l in wanted
                       if l.enabled and self._layer_has_data(l)])
        if output_file is None and self.is_grbl():
            job_layers = self.layers if kinds is None else [
                replace(l, enabled=l.enabled and l.kind in kinds) for l in self.layers]
            worker = GrblJobWorker(self.elements, job_layers, settings, self.values, self.laser, trace=trace,
                                   parent=self)
        elif trace:
            worker = JobWorker(self.design, settings, job.TRACE_ENG,
                               laser=None if output_file else self.laser,
                               output_file=output_file, send_options=send_options, parent=self,
                               origin=self.origin, bed=config.bed_size_inches(self.values))
        else:
            # only the chosen kinds: the others are switched off in the job's copy of the layers
            job_layers = self.layers if kinds is None else [
                replace(l, enabled=l.enabled and l.kind in kinds) for l in self.layers]
            worker = LayersJobWorker(self.elements, job_layers, settings, self._layer_cache,
                                     laser=None if output_file else self.laser,
                                     output_file=output_file, send_options=send_options, parent=self,
                                     bed=config.bed_size_inches(self.values))
        self._run_worker(worker, _("Preparing job\u2026"))

    def _run_worker(self, worker, message):
        import time
        self.worker = worker
        self._job_started = time.monotonic()
        self._set_paused(False)
        worker.progress.connect(self.status)
        worker.paused.connect(self._job_paused)
        worker.finished_job.connect(self._job_finished)
        self.set_busy(True)
        self.status(message)
        worker.start()

    def save_gcode(self):
        """File → Save G-code: the job as G-code for a GRBL laser (kerfly.core.gcode), after its options."""
        from kerfly.core import gcode
        from kerfly.gui.gcode_dialog import GcodeDialog
        if self.worker is not None:
            return
        if not self.elements:
            self.status(_("Nothing to save: open or draw something first."), error=True)
            return
        if self._off_bed_elements():
            self.status(_("Some elements stick out of the laser bed (drawn red): move them onto it first."),
                        error=True)
            return
        dlg = GcodeDialog(self.values, self)
        if not dlg.exec():
            return
        for key, value in dlg.values().items():
            self._set_value(key, value)
        self._store_profile()                        # the machine's G-code settings belong to its profile
        base = os.path.splitext(self.design_file)[0] if self.design_file else os.path.expanduser("~/out")
        name, _unused = QFileDialog.getSaveFileName(self, _("Save G-code"), base + ".nc",
                                                    _("G-code files") + " (*.nc *.gcode *.gc *.ngc)")
        if not name:
            return
        options = gcode.GcodeOptions(origin=self.values["gcode_origin"], s_max=int(self.values["gcode_s_max"]),
                                     overscan_mm=float(self.values["gcode_overscan"]),
                                     air=is_true(self.values.get("grbl_air", "0")))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            text = gcode.build(self.elements, self.layers, self.job_settings(), self.values, options, __version__)
            with open(name, "w", encoding="utf-8") as f:
                f.write(text)
        except (OSError, ValueError) as e:
            QApplication.restoreOverrideCursor()
            self.status(_("G-code not saved: %s") % e, error=True)
            return
        QApplication.restoreOverrideCursor()
        self.status(_("G-code saved: %s (%d lines)") % (name, text.count("\n")))

    def save_egv(self):
        base = os.path.splitext(self.design_file)[0] if self.design_file else os.path.expanduser("~/out")
        name, _unused = QFileDialog.getSaveFileName(self, _("Save EGV file"), base + ".EGV", _("EGV files (*.EGV *.egv)"))
        if name:
            self.start_job(output_file=name)

    def stop_job(self):
        if self.worker is not None:
            self.status(_("Stopping\u2026"))
            self.worker.request_stop()

    def pause_job(self):
        """Pause the running laser job, or resume it if it is paused."""
        if self.worker is None or self.worker.laser is None:
            return
        if self._paused:
            self.worker.resume()
            self._set_paused(False)
            self.status(_("Resumed"))
        else:
            self.btn_pause.setEnabled(False)          # until the board confirms the pause
            self.status(_("Pausing\u2026"))
            self.worker.request_pause()

    def _job_paused(self):
        self._set_paused(True)
        self.status(_("Paused. Press the pause button again to continue, or Stop to end the job."))

    def _set_paused(self, paused):
        self._paused = paused
        self.btn_pause.setEnabled(self.worker is not None and self.worker.laser is not None)
        self.btn_pause.setIcon(icons.tabler("player-play" if paused else "player-pause",
                                            theme.token("ok") if paused else None))
        self.btn_pause.setText(C_("job", "Resume") if paused else C_("job", "Pause"))
        self.btn_pause.setToolTip(_("Resume the job") if paused else _("Pause the laser; press again to resume"))

    def _job_finished(self, ok, message):
        was_laser_job = isinstance(self.worker, (JobWorker, LayersJobWorker, EgvSendWorker, GrblJobWorker)) \
            and self.worker.laser is not None
        interrupted = was_laser_job and not ok and self.worker.sending
        # a boundary trace checks where the job goes: no homing after it (the job starts there next)
        traced = isinstance(self.worker, (JobWorker, GrblJobWorker)) and \
            getattr(self.worker, "operation", None) == job.TRACE_ENG
        self.worker.wait()
        self.worker = None
        self._set_paused(False)
        self.set_busy(False)
        self.status(message, error=not ok)
        if interrupted:
            # the K40 does not report where the head is: after a stop it is somewhere in the job,
            # not back at the start where Kerfly assumes it
            diag_log.warning("job interrupted: head position unknown until Home")
            self.status(_("%s The laser head position is now unknown: press Home before the next job.")
                        % tr_message(message), error=True)
        if was_laser_job and self.laser.connected:
            if ok and not traced and is_true(self.values.get("post_home_xy", "0")):
                # back to 0, 0 for the next piece (only after a finished job: after Stop the head stays);
                # the design stays where it is, the next Start drives the head to it
                try:
                    self.laser.home()
                    self.head = self._home_head()
                    diag_log.info("job finished: head homed (setting)")
                except Exception as e:
                    self.status(_("The job is finished, but homing failed: %s") % e, error=True)
            if is_true(self.values.get("post_home", "0")):         # K40 Whisperer's name: it unlocks the rail
                try:
                    self.laser.unlock()
                except Exception:
                    pass
            if is_true(self.values.get("post_beep", "0")):
                QApplication.beep()
            if ok and not traced:
                self._after_job()
        self.refresh_preview()

    # ------------------------------------------------------------ after a job: report, program
    def _after_job(self):
        """A finished laser job: run the chosen program (Settings → Machine), show the report window
        with the job's time and the program's output (K40 Whisperer's Popup Report and Run Batch File)."""
        import time
        elapsed = time.monotonic() - getattr(self, "_job_started", time.monotonic())
        text = _("The job is finished.") + "\n" + _("Job time: %s") % format_time(elapsed)
        diag_log.info("job finished in %.1f s", elapsed)
        program = str(self.values.get("batch_path", "")).strip()
        if is_true(self.values.get("post_exec", "0")) and program:
            self._run_after_job_program(program, text)
        elif is_true(self.values.get("post_disp", "1")):
            self._show_job_report(text)

    def _program_process(self, program):
        """A QProcess for a program or script chosen in Settings → Machine (.bat through cmd on
        Windows, a .sh without the run permission through sh)."""
        import sys
        from PySide6.QtCore import QProcess
        proc = QProcess(self)
        if sys.platform == "win32" and program.lower().endswith((".bat", ".cmd")):
            proc.setProgram(os.environ.get("COMSPEC", "cmd.exe"))
            proc.setArguments(["/c", program])
        elif not sys.platform == "win32" and program.endswith(".sh") and not os.access(program, os.X_OK):
            proc.setProgram("/bin/sh")
            proc.setArguments([program])
        else:
            proc.setProgram(program)
        return proc

    @staticmethod
    def _program_result(proc, program, timed_out=False):
        """(output, error text or '') of a finished program."""
        from PySide6.QtCore import QProcess
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
        err = bytes(proc.readAllStandardError()).decode("utf-8", "replace").strip()
        if timed_out:
            err = _("The program did not end within a minute and was stopped: %s") % program + \
                ("\n" + err if err else "")
        elif proc.error() == QProcess.FailedToStart:
            err = (_("The program could not be started: %s") % program) + ("\n" + err if err else "")
        elif proc.exitStatus() != QProcess.NormalExit or proc.exitCode() != 0:
            err = (_("The program ended with an error (exit code %d).") % proc.exitCode()) + \
                ("\n" + err if err else "")
        return out, err

    def _run_before_job_program(self, program, start):
        """Run the program before a job; start() when it ended well, otherwise ask."""
        from PySide6.QtCore import QProcess
        proc = self._program_process(program)
        self._before_job_process = proc
        timer = QTimer(self)
        timer.setSingleShot(True)
        state = {"timed_out": False}

        def too_long():
            state["timed_out"] = True
            proc.kill()

        def done(*_args):
            if getattr(self, "_before_job_process", None) is not proc:
                return
            self._before_job_process = None
            timer.stop()
            self.set_busy(False)
            out, err = self._program_result(proc, program, state["timed_out"])
            diag_log.info("before-job program %s: out %r, err %r", program, out[:200], err[:200])
            proc.deleteLater()
            if not err:
                start()
                return
            self.status(_("The program run before the job reported an error."), error=True)
            answer = widgets.ask(
                self, _("Program before the job"),
                _("The program set to run before the job did not work:") + "\n\n" + err + "\n\n" +
                _("Start the job anyway?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                names={QMessageBox.Yes: _("Start anyway")})
            if answer == QMessageBox.Yes:
                start()
        timer.timeout.connect(too_long)
        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda e: done() if e == QProcess.FailedToStart else None)
        self.set_busy(True)
        self.status(_("Running the program set to run before a job: %s") % program)
        timer.start(60000)
        proc.start()

    def _run_after_job_program(self, program, text):
        from PySide6.QtCore import QProcess
        proc = self._program_process(program)
        self._after_job_process = proc

        def done(*_args):
            if getattr(self, "_after_job_process", None) is not proc:
                return
            self._after_job_process = None
            out, err = self._program_result(proc, program)
            diag_log.info("after-job program %s: out %r, err %r", program, out[:200], err[:200])
            report = text
            if out:
                report += "\n\n" + _("Program output:") + "\n" + out
            if err:
                report += "\n\n" + _("Program errors:") + "\n" + err
                self.status(_("The program run after the job reported an error; see the report window."),
                            error=True)
            # errors are always shown, as in K40 Whisperer, even with the report window off
            if is_true(self.values.get("post_disp", "1")) or err:
                self._show_job_report(report, error=bool(err))
            proc.deleteLater()
        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda e: done() if e == QProcess.FailedToStart else None)
        self.status(_("Running the program set to run after a job: %s") % program)
        proc.start()

    def _show_job_report(self, text, error=False):
        """One report window, not blocking: it waits there until the user is back at the laser."""
        box = getattr(self, "_job_report", None)
        try:
            if box is not None:
                box.isVisible()
        except RuntimeError:
            box = None
        if box is None:
            box = QMessageBox(self)
            box.setWindowTitle(_("Job report"))
            box.setStandardButtons(QMessageBox.Ok)
            box.setWindowModality(Qt.NonModal)
            self._job_report = box
        box.setIcon(QMessageBox.Warning if error else QMessageBox.Information)
        box.setText(text)
        box.show()
        box.raise_()

    # ------------------------------------------------------------ misc
    # ------------------------------------------------------------ simulation
    def _open_simulation(self):
        """The simulation window when it is open, else None."""
        sim = getattr(self, "_simulation", None)
        try:
            return sim if sim is not None and sim.isVisible() else None
        except RuntimeError:
            return None                            # it was closed (and deleted)

    def _close_simulation(self):
        """New or Open: another design, the simulation of the old one closes."""
        sim = self._open_simulation()
        if sim is not None:
            sim.close()

    def simulate_job(self):
        from kerfly.gui.simulation import SimulationDialog, simulation_steps
        if self.worker is not None:
            return
        open_one = self._open_simulation()
        if open_one is not None:
            # one simulation at a time: a second click (or a double click) brings it to the front
            open_one.raise_()
            open_one.activateWindow()
            return
        try:
            steps = simulation_steps(self)
        except ValueError as e:
            self.status(str(e), error=True)
            return
        if not steps:
            self.status(_("Nothing to do: load a design and select at least one operation."), error=True)
            return
        dlg = SimulationDialog(self, steps)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        dlg.toggle()                              # start playing
        self._simulation = dlg

    # ------------------------------------------------------------ diagnostics
    def save_report(self):
        self._write_report()

    def _write_report(self):
        """Ask where to save the diagnostic report and save it; returns the
        file name, or None if cancelled or not saved."""
        from datetime import datetime
        from kerfly import selftest
        from kerfly.core import diag
        default = os.path.join(os.path.expanduser("~"),
                               "kerfly-report-%s.txt" % datetime.now().strftime("%Y%m%d-%H%M"))
        name, _unused = QFileDialog.getSaveFileName(self, _("Save diagnostic report"), default,
                                                    _("Text files") + " (*.txt)")
        if not name:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            diag.log.info("diagnostic report requested; laser connected: %s", self.laser.connected)
            text = diag.build_report(__version__, self.values, selftest.checks_without_window())
            with open(name, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, _("Save diagnostic report"), str(e))
            return None
        QApplication.restoreOverrideCursor()
        self.status(_("Diagnostic report saved: %s") % name)
        return name

    # ------------------------------------------------------------ new versions
    def check_updates_on_start(self):
        """At start (the program, not the tests): at most once a day, in the
        background, unless switched off in Settings → Advanced (on by default)."""
        import time
        from kerfly.core import updates
        if self.values.get("check_updates", "1") == "0":
            return
        try:
            last = float(self.values.get("update_last", "0") or 0)
        except ValueError:
            last = 0.0
        if time.time() - last < updates.CHECK_EVERY_S:
            return
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual=False, fetch=None):
        """Ask GitHub in the background. manual (Help → Check for updates): the
        answer is said in the status bar also when there is nothing new, and a
        skipped version is shown again."""
        import time
        from kerfly.gui.update_check import UpdateCheck
        if getattr(self, "_update_check", None) is not None and self._update_check.isRunning():
            return
        skipped = "" if manual else self.values.get("update_skip", "")
        if manual:
            self.status(_("Checking for a new version…"))
        check = UpdateCheck(__version__, skipped, self, fetch=fetch)
        self._update_manual = manual
        check.done.connect(self._update_checked)      # a method of the window: runs in the window's thread
        self._update_check = check
        if not manual:
            self.values["update_last"] = "%d" % time.time()
            self._remember_view()
        check.start()

    def _update_checked(self, release, error):
        manual = getattr(self, "_update_manual", False)
        if release is not None:
            self.update_bar.show_release(release, __version__)
            if manual:
                self.status(_("%s is available.") % release.name)
        elif manual:
            if error:
                self.status(_("Could not check for a new version: %s") % error, error=True)
            else:
                self.status(_("You have the newest version (%s).") % __version__)

    def _skip_update(self, version):
        self.values["update_skip"] = version
        self._remember_view()

    def _crop_values_changed(self, values):
        self.crop_defaults = dict(values)
        self.preview.crop_shape = values.get("crop_shape", "rect")

    def crop_picture(self, start, end):
        """Cut out of a picture tool: the piece of the picture inside the dragged rectangle or ellipse
        (scene mm) stays, in its place on the bed; the rest of the picture goes. One undo step."""
        from PySide6.QtCore import QPointF, QRectF
        from kerfly.core import crop
        from kerfly.core import loaders as _loaders
        from kerfly.gui.preview import element_transform
        x0, y0, x1, y1 = min(start.x(), end.x()), min(start.y(), end.y()), max(start.x(), end.x()), max(start.y(), end.y())
        if x1 - x0 < 0.5 or y1 - y0 < 0.5:
            self.status(_("Drag over a picture to cut a piece out of it."), error=True)
            return
        home_ur, bed_w_mm = self.preview.home_ur, self.preview.bed_w_mm
        outline = crop.outline_points(x0, y0, x1, y1, self.crop_defaults.get("crop_shape", "rect"))
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        candidates = [self.selected] if self.selected is not None else []
        candidates += list(reversed(self.elements))
        picture = None
        for e in candidates:
            if e is None or e.design.raster.image is None or not e.visible:
                continue
            t = element_transform(e, home_ur, bed_w_mm)
            if t.mapRect(QRectF(0, 0, *[(b - a) * 25.4 for a, b in ((e.design.bounds[0], e.design.bounds[1]),
                                                                     (e.design.bounds[2], e.design.bounds[3]))])) \
                    .contains(QPointF(cx, cy)):
                picture = e
                break
        if picture is None:
            self.status(_("Drag over a picture to cut a piece out of it."), error=True)
            return
        d = picture.design
        dpi = float(d.input_dpi)
        inverse, ok = element_transform(picture, home_ur, bed_w_mm).inverted()
        if not ok:
            return
        k = dpi / 25.4
        polygon = []
        for x, y in outline:
            p = inverse.map(QPointF(x, y))
            polygon.append((p.x() * k, p.y() * k))                     # local mm -> pixels of the picture
        result = crop.cut_out(d.raster.image, polygon)
        if result is None:
            self.status(_("Drag over a picture to cut a piece out of it."), error=True)
            return
        piece, (left, top) = result
        # where the middle of the piece is on the bed now
        t = element_transform(picture, home_ur, bed_w_mm)
        mid = t.map(QPointF((left + piece.width / 2.0) / k, (top + piece.height / 2.0) / k))
        path = self._save_generated_image(piece, os.path.splitext(picture.name)[0] + "-cut")
        design = Design()
        _loaders.load_image(path, design, dpi, False)
        design.input_dpi = dpi
        self._checkpoint()
        cut = Element(design, name=picture.name, source_file=path, load_options={"dpi": dpi},
                      layers=dict(picture.layers), group=picture.group)
        cut.scale_x, cut.scale_y, cut.rotation = picture.scale_x, picture.scale_y, picture.rotation
        bx = ((bed_w_mm - mid.x()) if home_ur else mid.x()) / 25.4
        cut.set_centre(bx, -mid.y() / 25.4)
        self.elements[self.elements.index(picture)] = cut
        self.selected = cut
        self._compiled = None
        self._layer_cache.clear()
        self._layout_changed()
        diag_log.info("cut out of %s: %d x %d px", picture.name, piece.width, piece.height)
        self.status(_("A piece was cut out of the picture (Undo brings the whole picture back)."))

    def trace_image(self):
        """Edit → Trace picture…: the dark areas of the selected picture as a new path element over it."""
        from kerfly.core import curves
        from kerfly.gui.trace_dialog import TraceDialog
        e = self.selected
        if e is None or e.design.raster.image is None:
            self.status(_("Select a picture to trace first."), error=True)
            return
        dlg = TraceDialog(e.design.raster.image, self)
        if not dlg.exec():
            return
        paths = dlg.result_paths()
        if not paths:
            self.status(_("Nothing to trace at this threshold."), error=True)
            return
        d = e.design
        dpi = float(d.input_dpi)
        xmin, _xmax, _ymin, ymax = d.bounds
        # pixels (y down) -> the picture's design (inches, y up) -> mm, y down, from the traced outline
        x0p, x1p, y0p, y1p = curves.bounds(paths)
        local = curves.translate(paths, -x0p, -y0p)
        k = 25.4 / dpi
        for sp in local:
            for nd in sp["nodes"]:
                for i in (0, 1, 2, 3, 4, 5):
                    if nd[i] is not None:
                        nd[i] *= k
        spec = ShapeSpec(kind="path", operation="engrave")
        spec.subpaths = local
        spec.width, spec.height = (x1p - x0p) * k, (y1p - y0p) * k
        design = build_design(spec)
        self._checkpoint()
        traced = Element(design, name=_("Trace of %s") % e.name, shape=spec)
        traced.scale_x, traced.scale_y, traced.rotation = e.scale_x, e.scale_y, e.rotation
        # its middle where that part of the picture is on the bed
        cx = xmin + (x0p + x1p) / 2.0 / dpi
        cy = ymax - (y0p + y1p) / 2.0 / dpi
        traced.set_centre(*e.transform()(cx, cy))
        self.elements.append(traced)
        self.selected = traced
        self._compiled = None
        self._layout_changed()
        diag_log.info("traced %s: %d paths", e.name, len(paths))
        self.status(_("Traced: %d outlines over the picture (Undo takes them away).") % len(paths))

    def show_shortcuts(self):
        """Help → Keyboard shortcuts: one window, not blocking; a second click brings it to the front."""
        from kerfly.gui.shortcuts_dialog import ShortcutsDialog
        dlg = getattr(self, "_shortcuts", None)
        try:
            if dlg is not None and dlg.isVisible():
                dlg.raise_()
                dlg.activateWindow()
                return
        except RuntimeError:
            pass
        dlg = ShortcutsDialog(self)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        self._shortcuts = dlg

    def open_guide(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from kerfly.core import diag
        from kerfly.i18n import current_language
        QDesktopServices.openUrl(QUrl(diag.guide_url(current_language())))

    def report_problem(self):
        """Save the diagnostic report, then open the GitHub issue form with the
        version, system and board filled in; the report is dragged into it."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from kerfly.core import diag
        box = QMessageBox(self)
        box.setWindowTitle(_("Report a problem"))
        box.setIcon(QMessageBox.Question)
        box.setText(_("What kind of problem is it?"))
        box.setInformativeText(_("Kerfly saves a diagnostic report and opens the report form on GitHub "
                                 "in your browser (a free GitHub account is needed to send it)."))
        laser = box.addButton(_("The laser did something wrong"), QMessageBox.AcceptRole)
        other = box.addButton(_("Another problem"), QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() not in (laser, other):
            return
        name = self._write_report()
        if not name:
            return
        kind = "laser" if box.clickedButton() is laser else "bug"
        QDesktopServices.openUrl(QUrl(diag.issue_url(kind, __version__, self.values.get("board_name", ""))))
        info = QMessageBox(self)
        info.setWindowTitle(_("Report a problem"))
        info.setIcon(QMessageBox.Information)
        info.setText(_("The report form is opening in your browser. Please drag the diagnostic report "
                       "into its \"Diagnostic report\" field:"))
        info.setInformativeText(name)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        folder = info.addButton(_("Show the report file"), QMessageBox.ActionRole)
        info.addButton(QMessageBox.Close)
        info.exec()
        if info.clickedButton() is folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(name)))

    def open_log_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from kerfly.core import diag
        folder = os.path.dirname(diag.log_path())
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def about(self):
        from kerfly.gui.about_dialog import AboutDialog
        AboutDialog(self).exec()

    def closeEvent(self, event):
        if self.worker is None and not self._confirm_discard():
            event.ignore()
            return
        if self.worker is not None:
            if widgets.ask(self, _("Job running"), _("A job is running. Stop it and quit?"),
                           names={QMessageBox.Yes: _("Stop and quit")}, danger=True) != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.stop[0] = True
            self.worker.pause.terminate()
            self.worker.wait(5000)
        try:
            self.laser.release()
        except Exception:
            pass
        self._save_window_geometry()
        event.accept()
