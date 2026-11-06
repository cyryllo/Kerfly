"""
"The window tells the truth": checks that what the main window shows is what
its data holds. Used by the release tests after every step of a session
(tests/test_release.py, tests/test_gui.py) and by `--release-test`.

check_window(w) returns a list of problems (empty: all fine). Every check works
out what should be shown from the data on its own, not with the window's code,
so a field that was not refreshed, shows another element or is missing is
found:

- options bar: every field (marked with the "spec_attr" property) shows the
  value of the selected shape, of the tool in use or of the tool's defaults,
  and the fields that belong to the shape are there;
- position, size and rotation fields: the selected element's real values;
- element list: one row per element, in order, with its name, tick and
  layers, and the selected rows are the selected elements;
- layer choice above the bed: the layers the selected element's parts are on;
- layers panel: a row for every layer that has something on it, with its
  settings;
- bed view: one item per element, where the element is, selected as it is;
- job: the compiled design covers exactly the visible elements.

state(w) is a comparable picture of the document (elements, shapes, layers),
for undo / redo and save / open checks.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from dataclasses import asdict, fields

from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QDoubleSpinBox, QFontComboBox, QPlainTextEdit,
                               QSpinBox, QToolButton, QWidget)

from kerfly.core.layers import CUT, ENGRAVE, GCODE, RASTER, layer_of, part_present

MM = 25.4
FILL_ATTRS = ("fill_pattern", "fill_spacing", "fill_angle", "fill_margin", "fill_outline")
HINGE_ATTRS = ("hinge_pattern", "hinge_cut", "hinge_gap", "hinge_spacing", "hinge_angle", "hinge_margin",
               "hinge_band", "hinge_band_offset")
TEXT_ATTRS = ("text", "font_family", "font_size", "bold", "italic", "text_spacing")
TEXT_PATH_ATTRS = ("text_path_offset", "text_path_flip", "text_path_distance")
OPERATION_KIND = {"cut": CUT, "engrave": ENGRAVE, "fill": RASTER, "hatch": ENGRAVE}


# ---------------------------------------------------------------- options bar
def bar_fields(bar):
    """{setting name: widget} of the fields on the options bar now."""
    out = {}
    for widget in bar.findChildren(QWidget):
        attr = widget.property("spec_attr")
        if attr and not widget.isHidden():
            out[str(attr)] = widget
    return out


def shown_value(widget):
    if isinstance(widget, QComboBox) and not isinstance(widget, QFontComboBox):
        return widget.currentData()
    if isinstance(widget, QFontComboBox):
        return widget.currentFont().family()
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QPlainTextEdit):
        return widget.toPlainText()
    if isinstance(widget, QToolButton):
        return widget.isChecked()
    raise TypeError("unknown field %r" % widget)


def _same(widget, shown, wanted):
    if isinstance(widget, QDoubleSpinBox):
        wanted = min(max(float(wanted), widget.minimum()), widget.maximum())
        return abs(shown - wanted) <= 0.5 * 10 ** -widget.decimals() + 1e-9
    if isinstance(widget, QSpinBox):
        return shown == min(max(int(wanted), widget.minimum()), widget.maximum())
    if isinstance(widget, QToolButton):
        return bool(shown) == bool(wanted)
    if isinstance(widget, QFontComboBox):
        from PySide6.QtGui import QFontDatabase
        if wanted not in QFontDatabase.families() or widget.count() == 0:
            return True                         # not installed here (or no font list without a screen)
        return shown == wanted
    return (shown or "") == (wanted or "")


def _fill_like(w, tool):
    """What the Fill / Living hinge tool bar must show, worked out from the data:
    the selected shape it applies to (its own settings, "none" without one), or
    the tool's settings when no such shape is selected."""
    if tool == "fill":
        attrs, defaults = FILL_ATTRS, w.fill_defaults
        fits = lambda e: e.shape is not None and e.shape.closed and e.shape.operation in ("cut", "engrave", "hatch")
    else:
        attrs, defaults = HINGE_ATTRS, w.hinge_defaults
        fits = lambda e: (e.shape is not None and e.shape.kind != "text" and e.shape.closed
                          and e.shape.operation in ("cut", "engrave"))
    chosen = [e for e in w._selection() if fits(e)]
    if not chosen:
        return {a: getattr(defaults, a) for a in attrs}, set(attrs)
    e = w.selected if w.selected in chosen else chosen[0]
    if getattr(e.shape, attrs[0]):
        return {a: getattr(e.shape, a) for a in attrs}, set(attrs)
    wanted = {a: getattr(defaults, a) for a in attrs[1:]}
    wanted[attrs[0]] = ""
    return wanted, set(attrs)


def expected_bar(w):
    """(values {setting: value} the bar must show, settings that must be there),
    or (None, set()) when the bar must be empty. Worked out from the window's
    data and the tool in use."""
    tool = w.preview.tool
    if tool in ("fill", "hinge"):
        return _fill_like(w, tool)
    e = w.selected
    if tool == "textpath":
        if e is not None and e.shape is not None and e.shape.kind == "text":
            spec = e.shape
        else:
            spec = w.shape_defaults["textpath"]
    elif e is not None and e.shape is not None:
        spec = e.shape
    elif tool in w.shape_defaults and tool != "nodes":
        spec = w.shape_defaults[tool]
    else:
        return None, set()
    names = {f.name for f in fields(spec)}
    values = {a: getattr(spec, a) for a in names}
    must = set()
    if spec.operation == "cut" and spec.closed:
        must |= {"tabs", "tab_width"}
    if spec.operation in ("cut", "engrave") and spec.closed:
        must.add("fill_pattern")
        if spec.fill_pattern:
            must |= set(FILL_ATTRS)
        if spec.hinge_pattern:
            must |= set(HINGE_ATTRS)
    if spec.kind == "rectangle":
        must.add("corner_radius")
    elif spec.kind == "polygon":
        must.add("sides")
    elif spec.kind == "text":
        must |= set(TEXT_ATTRS)
        if spec.text_path:
            must |= set(TEXT_PATH_ATTRS)
    return values, must


def check_bar(w):
    problems = []
    bar = w.tool_options
    shown = bar_fields(bar)
    wanted, must = expected_bar(w)
    where = "options bar (tool %s, selected %s)" % (w.preview.tool, w.selected.name if w.selected else "none")
    if wanted is None:
        if shown:
            problems.append("%s: should be empty, shows %s" % (where, sorted(shown)))
        return problems
    for attr in sorted(must - set(shown)):
        problems.append("%s: field '%s' is missing" % (where, attr))
    for attr in sorted(set(shown) - set(wanted)):
        problems.append("%s: field '%s' does not belong here" % (where, attr))
    for attr, widget in sorted(shown.items()):
        if attr not in wanted:
            continue
        if attr == "text" and bar._text_timer.isActive():
            continue                            # typing: applied when the typing pauses
        value = shown_value(widget)
        if not _same(widget, value, wanted[attr]):
            problems.append("%s: '%s' shows %r, should be %r" % (where, attr, value, wanted[attr]))
    return problems


# ---------------------------------------------------------- other panels
def check_selection_fields(w):
    problems = []
    e = w.selected
    if e is None:
        if w.selection_box.isEnabled():
            problems.append("position fields: enabled with nothing selected")
        return problems
    if not w.selection_box.isEnabled():
        problems.append("position fields: disabled although %s is selected" % e.name)
    k = w._units_per_inch()
    width, height = e.size
    wanted = {"x": e.x * k, "y": -e.y * k, "w": width * k, "h": height * k}
    for key, spin in w.sel_fields.items():
        if abs(spin.value() - wanted[key]) > 0.5 * 10 ** -spin.decimals() + 1e-6:
            problems.append("position fields: %s shows %.3f, %s has %.3f" % (key, spin.value(), e.name, wanted[key]))
    rotation = e.rotation % 360
    rotation = rotation if rotation <= 180 else rotation - 360
    if abs(w.sel_rotation.value() - rotation) > 0.5 * 10 ** -w.sel_rotation.decimals() + 1e-6:
        problems.append("rotation field shows %.2f, %s is turned %.2f" % (w.sel_rotation.value(), e.name, rotation))
    return problems


def chosen_elements(w):
    """The elements the window treats as selected (several on the bed, or the one)."""
    chosen = [e for e in w.preview.selected_elements() if e in w.elements]
    if not chosen and w.selected is not None:
        chosen = [w.selected]
    return chosen


def _parts(e):
    return [k for k in (RASTER, ENGRAVE, CUT, GCODE) if e.design is not None and part_present(e.design, k)]


def check_element_list(w):
    problems = []
    lst = w.element_list
    if lst.count() != len(w.elements):
        return ["element list: %d rows for %d elements" % (lst.count(), len(w.elements))]
    if w.element_list_box.isHidden() == bool(w.elements):
        problems.append("element list: %s with %d elements" % ("hidden" if w.elements else "shown", len(w.elements)))
    chosen = {id(e) for e in chosen_elements(w)}
    from PySide6.QtCore import Qt
    for row, e in enumerate(w.elements):
        item = lst.item(row)
        text = item.text()
        if e.name not in text:
            problems.append("element list row %d: '%s' is not %s" % (row + 1, text, e.name))
        for kind in _parts(e):
            layer = layer_of(e, kind, w.layers)
            if layer is not None and layer.name not in text:
                problems.append("element list row %d: layer %s of %s missing in '%s'"
                                % (row + 1, layer.name, e.name, text))
        if (item.checkState() == Qt.Checked) != e.visible:
            problems.append("element list row %d: tick %s, %s is %s" % (
                row + 1, item.checkState() == Qt.Checked, e.name, "in the job" if e.visible else "left out"))
        if item.isSelected() != (id(e) in chosen):
            problems.append("element list row %d (%s): %s in the list, %s on the bed" % (
                row + 1, e.name, "selected" if item.isSelected() else "not selected",
                "selected" if id(e) in chosen else "not selected"))
    return problems


def check_layer_choice(w):
    """The layer lists above the bed show the layers of the selected element's parts."""
    problems = []
    e = w.selected
    combos = [c for c in w.layer_assign_box.findChildren(QComboBox) if not c.isHidden()]
    if e is None:
        if combos:
            problems.append("layer choice: %d lists with nothing selected" % len(combos))
        return problems
    if e.shape is not None:
        kinds = [OPERATION_KIND.get(e.shape.operation, CUT)]
        from kerfly.core.shapes import has_pattern_fill
        if has_pattern_fill(e.shape) and e.shape.operation == "cut":
            kinds.append(ENGRAVE)
    else:
        kinds = _parts(e)
    if len(combos) != len(kinds):
        return ["layer choice for %s: %d lists, %d parts" % (e.name, len(combos), len(kinds))]
    order = {c: (w.layer_assign_box.layout().getItemPosition(w.layer_assign_box.layout().indexOf(c)))
             for c in combos}
    combos.sort(key=lambda c: (order[c][1], order[c][0]))
    for combo, kind in zip(combos, kinds):
        layer = layer_of(e, kind, w.layers)
        if layer is not None and combo.currentData() != layer.id:
            problems.append("layer choice for %s (%s): shows %s, part is on %s"
                            % (e.name, kind, combo.currentText(), layer.name))
    return problems


def check_layers_panel(w):
    problems = []
    rows = w.layers_panel.rows
    for layer in w.layers:
        if w._layer_has_data(layer) and layer.id not in rows:
            problems.append("layers panel: %s has parts on it but no row" % layer.name)
        row = rows.get(layer.id)
        if row and "speed" in row and abs(row["speed"].value() - layer.speed) > 0.05 + 1e-9:
            problems.append("layers panel: %s speed shows %.1f, is %.1f" % (layer.name, row["speed"].value(),
                                                                          layer.speed))
    return problems


def check_bed_view(w):
    problems = []
    items = list(w.preview._items)
    if [i.element for i in items] != list(w.elements):
        return ["bed view: %d items for %d elements (or another order)" % (len(items), len(w.elements))]
    bed_w_mm = w.preview.bed_w_mm
    chosen = {id(e) for e in w.preview.selected_elements()}
    for item in items:
        e = item.element
        r = item.sceneBoundingRect()
        xmin, xmax, ymin, ymax = e.bounds
        left = xmin * MM
        if w.preview.home_ur:
            left = bed_w_mm - xmax * MM
        top = -ymax * MM
        tol = 0.05 + 0.002 * max(r.width(), r.height())
        if abs(r.left() - left) > tol or abs(r.top() - top) > tol or \
                abs(r.width() - (xmax - xmin) * MM) > tol or abs(r.height() - (ymax - ymin) * MM) > tol:
            problems.append("bed view: %s drawn at (%.2f, %.2f) %.2f x %.2f mm, is at (%.2f, %.2f) %.2f x %.2f mm"
                            % (e.name, r.left(), r.top(), r.width(), r.height(), left, top,
                               (xmax - xmin) * MM, (ymax - ymin) * MM))
        if (item.opacity() < 1.0) == e.visible:
            problems.append("bed view: %s drawn %s, it is %s" % (
                e.name, "faded" if item.opacity() < 1.0 else "normal", "in the job" if e.visible else "left out"))
        if item.isSelected() != (id(e) in chosen):
            problems.append("bed view: selection of %s changed under the window" % e.name)
    if w.selected is not None and w.selected not in w.elements:
        problems.append("the selected element %s is not on the bed" % w.selected.name)
    return problems


def check_job(w):
    """The compiled design covers the visible elements (where the job runs)."""
    visible = [e for e in w.elements if e.visible]
    if not visible:
        return []
    w._compiled = None                          # compile now, as Start would
    design = w.design
    x0 = min(e.bounds[0] for e in visible)
    x1 = max(e.bounds[1] for e in visible)
    y0 = min(e.bounds[2] for e in visible)
    y1 = max(e.bounds[3] for e in visible)
    ox, oy = w.origin
    bx0, bx1, by0, by1 = design.bounds
    tol = 0.3 / MM + 0.002 * max(x1 - x0, y1 - y0)
    problems = []
    if abs(ox - x0) > tol or abs(oy - y1) > tol:
        problems.append("job: starts at (%.2f, %.2f) mm, the elements start at (%.2f, %.2f) mm"
                        % (ox * MM, -oy * MM, x0 * MM, -y1 * MM))
    if abs((bx1 - bx0) - (x1 - x0)) > tol or abs((by1 - by0) - (y1 - y0)) > tol:
        problems.append("job: %.2f x %.2f mm, the elements cover %.2f x %.2f mm"
                        % ((bx1 - bx0) * MM, (by1 - by0) * MM, (x1 - x0) * MM, (y1 - y0) * MM))
    return problems


CHECKS = (check_bar, check_selection_fields, check_element_list, check_layer_choice, check_layers_panel,
          check_bed_view, check_job)


def check_window(w, job=True):
    """All checks; a list of problems (empty: the window tells the truth)."""
    problems = []
    for check in CHECKS:
        if check is check_job and not job:
            continue
        try:
            problems += check(w)
        except Exception as exc:                 # a broken check is a problem too
            problems.append("%s failed: %r" % (check.__name__, exc))
    return problems


# --------------------------------------------------------------- document state
def _round(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return [_round(x) for x in v]
    if isinstance(v, dict):
        return {k: _round(x) for k, x in v.items()}
    return v


def state(w):
    """The document as plain data: equal states mean the same project (layer ids
    replaced by their place in the list, so a reopened project compares equal)."""
    index = {layer.id: n for n, layer in enumerate(w.layers)}
    layers = [(l.kind, l.name, l.color, round(l.speed, 3), l.passes, round(l.power, 3), l.enabled) for l in w.layers]
    elements = []
    for e in w.elements:
        shape = asdict(e.shape) if e.shape is not None else None
        elements.append(_round({"name": e.name, "placement": list(e.placement()), "shape": shape,
                                "layers": {k: index.get(v, v) for k, v in sorted(e.layers.items())},
                                "group": bool(e.group), "source": e.source_file,
                                "bounds": list(e.design.bounds) if e.design is not None else None}))
    groups = {}
    for e in w.elements:                         # group ids are random: compare who is with whom
        if e.group:
            groups.setdefault(e.group, []).append(w.elements.index(e))
    return {"layers": layers, "elements": elements, "groups": sorted(groups.values())}


def difference(a, b):
    """First difference between two states, as text (empty: equal)."""
    if a == b:
        return ""
    if a["layers"] != b["layers"]:
        return "layers: %r != %r" % (a["layers"], b["layers"])
    if len(a["elements"]) != len(b["elements"]):
        return "%d elements != %d" % (len(a["elements"]), len(b["elements"]))
    for n, (x, y) in enumerate(zip(a["elements"], b["elements"])):
        if x != y:
            for key in x:
                if x[key] != y.get(key):
                    if key == "shape" and x[key] and y[key]:
                        diff = [k for k in x[key] if x[key][k] != y[key].get(k)]
                        return "element %d (%s): shape %s: %r != %r" % (
                            n + 1, x["name"], diff[0], x[key][diff[0]], y[key][diff[0]])
                    return "element %d (%s): %s: %r != %r" % (n + 1, x["name"], key, x[key], y.get(key))
    return "groups: %r != %r" % (a["groups"], b["groups"])
