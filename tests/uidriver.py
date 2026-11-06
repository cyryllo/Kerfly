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


def bar_set(w, attr, value):
    """Change a field of the options bar as a user does (type a number, pick from
    a list, press a button, type a text)."""
    widget = bar_field(w, attr)
    bar = w.tool_options
    if isinstance(widget, QFontComboBox):
        from PySide6.QtGui import QFont
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
