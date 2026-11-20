"""
Drive the main window the way a user does: select on the bed, change a field
of the options bar, pick from a list. The tests use these instead of setting
the window's data directly, so what the window shows is checked too
(kerfly.gui.truth).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import QApplication, QComboBox, QFontComboBox, QPlainTextEdit, QToolButton

from kerfly.gui.truth import bar_fields


def settle(n=5):
    for _ in range(n):
        QApplication.processEvents()


def select(w, *elements):
    """Click elements on the bed (several: like a frame drawn around them); none: click the empty bed."""
    w.preview.select_element(list(elements))
    settle(2)


def bar_field(w, attr):
    fields = bar_fields(w.tool_options)
    if attr not in fields:
        raise KeyError("the options bar has no field '%s' now (it has %s)" % (attr, sorted(fields)))
    return fields[attr]


TEXT_ATTRS = {"text", "font_family", "font_size", "bold", "italic", "text_spacing", "text_path_offset",
              "text_path_distance", "text_path_flip"}
FILL_ATTRS = {"fill_pattern", "fill_spacing", "fill_angle", "fill_margin", "fill_outline"}
HINGE_ATTRS = {"hinge_pattern", "hinge_cut", "hinge_gap", "hinge_spacing", "hinge_angle", "hinge_margin",
               "hinge_band", "hinge_band_offset"}


def dialog_set(dlg, attr, value):
    """Set a field of a tool's window as a user does (a tile clicked, a number typed, a box ticked)."""
    from PySide6.QtWidgets import QCheckBox
    if attr in ("fill_pattern", "hinge_pattern", "offset_join"):
        dlg.tiles.buttons[value].click()
        return
    widget = dlg.fields[attr]
    if isinstance(widget, QFontComboBox):
        widget.set_family(value)
    elif isinstance(widget, QPlainTextEdit):
        widget.setPlainText(value)
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    else:
        widget.setValue(value)


def window_set(w, attr, value):
    """A setting kept in a tool's window (the text, a fill, a hinge) changed through that window: it opens for
    the selected shape, the field is set, its action clicked ("" for a pattern: its Remove button)."""
    import kerfly.gui.tool_dialogs as td
    saved = td.answer

    def answer(dlg):
        if attr in ("fill_pattern", "hinge_pattern") and not value:
            dlg.removed = True
            return True
        dialog_set(dlg, attr, value)
        return True
    td.answer = answer
    try:
        e = w.selected
        if attr in TEXT_ATTRS:
            w.edit_text(e)
        else:
            w._open_tool_window("fill" if attr in FILL_ATTRS else "hinge", w._selection() or [e])
    finally:
        td.answer = saved
    settle()


def window_answers(**values):
    """A context: the tool windows opened inside it get these values (tiles clicked, fields set) and their
    action clicked; remove=True: their Remove button."""
    from contextlib import contextmanager
    import kerfly.gui.tool_dialogs as td

    @contextmanager
    def ctx():
        saved = td.answer
        seen = []

        def answer(dlg):
            seen.append(dlg)
            if values.get("remove"):
                dlg.removed = True
                return True
            for attr, value in values.items():
                if attr != "remove":
                    dialog_set(dlg, attr, value)
            dlg.refresh()
            return True
        td.answer = answer
        try:
            yield seen
        finally:
            td.answer = saved
            settle()
    return ctx()


def bar_set(w, attr, value):
    """Change a field of the options bar as a user does (type a number, pick from
    a list, press a button, type a text); a text's, a fill's or a hinge's setting through its window."""
    if attr not in bar_fields(w.tool_options) and attr in TEXT_ATTRS | FILL_ATTRS | HINGE_ATTRS:
        window_set(w, attr, value)
        return
    widget = bar_field(w, attr)
    bar = w.tool_options
    if isinstance(widget, QFontComboBox):
        from PySide6.QtGui import QFont
        if hasattr(widget, "set_family"):
            widget.set_family(value)            # also Kerfly's single-line fonts
        else:
            widget.setCurrentFont(QFont(value))
    elif isinstance(widget, QComboBox):
        index = widget.findData(value)
        if index < 0:
            raise ValueError("'%s' has no choice %r" % (attr, value))
        widget.setCurrentIndex(index)
        widget.activated.emit(index)            # a choice from the open list (also the one already shown)
    elif isinstance(widget, QToolButton):
        if widget.isChecked() != bool(value):
            widget.click()
    elif isinstance(widget, QPlainTextEdit):
        widget.setPlainText(value)
        if bar._text_timer.isActive():          # as if the typing paused
            bar._text_timer.stop()
            bar._text_timer.timeout.emit()
    else:
        widget.setValue(value)                  # typed and confirmed (Enter / leaving the field)
    settle()


def click_bar_button(w, text):
    """Press a button of the options bar by its caption (e.g. "Straight text")."""
    buttons = [b for b in w.tool_options.findChildren(QToolButton) if b.text() == text and not b.isHidden()]
    if not buttons:
        raise KeyError("the options bar has no button '%s'" % text)
    buttons[0].click()
    settle()


def choose_layer(w, layer, row=0):
    """Pick a layer in the Layer list above the bed (row 1: the fill pattern's list)."""
    grid = w.layer_assign_box.layout()
    item = grid.itemAtPosition(row, 0)
    combo = item.widget() if item is not None else None
    if not isinstance(combo, QComboBox):
        raise KeyError("no layer list in row %d above the bed" % row)
    index = combo.findData(layer.id)
    if index < 0:
        raise ValueError("layer %s is not in the list" % layer.name)
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    settle()
