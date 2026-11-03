"""
Widget widths computed from the widget's font instead of fixed pixels, so the
layout fits with any desktop font, font size and language.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""


def _spin_text(spin, value):
    return spin.prefix() + spin.textFromValue(value) + spin.suffix()


def fit_spin(spin, value):
    """Fix a spin box's width so that `value` (with prefix/suffix) fits.

    The frame and arrow-button overhead is taken from the style's own size hint,
    so this works for every style and font. Call refit_spin() after changing
    the suffix."""
    spin.setProperty("fit_value", value)
    fm = spin.fontMetrics()
    widest = max(fm.horizontalAdvance(_spin_text(spin, spin.minimum())),
                 fm.horizontalAdvance(_spin_text(spin, spin.maximum())))
    overhead = spin.sizeHint().width() - widest
    spin.setFixedWidth(fm.horizontalAdvance(_spin_text(spin, value)) + max(overhead, 24))
    return spin


def refit_spin(spin):
    value = spin.property("fit_value")
    if value is not None:
        spin.setMinimumWidth(0)
        spin.setMaximumWidth(16777215)
        fit_spin(spin, value)


def chars_width(widget, chars):
    """Width of `chars` average characters in the widget's font."""
    return widget.fontMetrics().averageCharWidth() * chars
