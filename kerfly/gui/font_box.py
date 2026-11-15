"""
The font list of the Text tool: Kerfly's single-line fonts (for fast engraving)
at the top, then the fonts installed on the system.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFontComboBox

from kerfly.core import stroke_fonts


class FontBox(QFontComboBox):
    """A QFontComboBox that also offers the single-line fonts (they are not system fonts, so
    QFontComboBox alone would replace their names by the nearest installed font).

    family() is the family as listed (QFontComboBox's own currentFont() can be a generic alias such as
    "Sans Serif" on a computer with few fonts); family_chosen(str) tells every choice, also of a family
    that is not in the list (a computer without that font): the text keeps the family it asked for."""
    family_chosen = Signal(str)

    def __init__(self, single_line=True, parent=None):
        super().__init__(parent)
        self.single_line = stroke_fonts.families() if single_line else []
        self._wanted = None
        self._missing = None                  # a family asked for that the list does not have
        self._add_single_line()
        # QFontComboBox fills its list again by itself (when shown, when fonts change): put them back
        self.model().modelReset.connect(self._add_single_line)
        self.currentIndexChanged.connect(self._index_changed)

    def _add_single_line(self):
        if not self.single_line or self.findText(self.single_line[0]) >= 0:
            return
        self.blockSignals(True)
        for i, name in enumerate(self.single_line):
            self.insertItem(i, name)
        if self._wanted is not None and self.findText(self._wanted) >= 0:
            self.setCurrentIndex(self.findText(self._wanted))
        self.blockSignals(False)

    def _index_changed(self, _index):
        self._missing = None
        self.family_chosen.emit(self.family())

    def family(self):
        if self._missing:
            return self._missing
        return self.currentText() or self.currentFont().family()

    def set_family(self, family):
        self._add_single_line()                 # first, quietly; then the choice, which tells the bar
        self._wanted = family
        index = self.findText(family)
        if index >= 0:
            if index != self.currentIndex():
                self.setCurrentIndex(index)
            elif self._missing:
                self._missing = None
                self.family_chosen.emit(family)
            return
        # not in this computer's list (no such font here): the nearest one is shown, the family is kept
        self.blockSignals(True)
        self.setCurrentFont(QFont(family))
        current = self.currentText()
        self.blockSignals(False)
        self._add_single_line()
        self.blockSignals(True)
        if current:
            self.setCurrentIndex(max(0, self.findText(current)))
        self.blockSignals(False)
        changed = self._missing != family
        self._missing = family
        if changed:
            self.family_chosen.emit(family)
