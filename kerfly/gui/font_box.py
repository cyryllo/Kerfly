"""
The font list of the Text tool: Kerfly's single-line fonts (for fast engraving)
at the top, then the fonts installed on the system.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFontComboBox

from kerfly.core import stroke_fonts


class FontBox(QFontComboBox):
    """A QFontComboBox that also offers the single-line fonts (they are not system fonts, so
    QFontComboBox alone would replace their names by the nearest installed font)."""

    def __init__(self, single_line=True, parent=None):
        super().__init__(parent)
        self.single_line = stroke_fonts.families() if single_line else []
        self._wanted = None
        self._add_single_line()
        # QFontComboBox fills its list again by itself (when shown, when fonts change): put them back
        self.model().modelReset.connect(self._add_single_line)

    def _add_single_line(self):
        if not self.single_line or self.findText(self.single_line[0]) >= 0:
            return
        self.blockSignals(True)
        for i, name in enumerate(self.single_line):
            self.insertItem(i, name)
        if self._wanted in self.single_line:
            self.setCurrentIndex(self.findText(self._wanted))
        self.blockSignals(False)

    def family(self):
        text = self.currentText()
        return text if text in self.single_line else self.currentFont().family()

    def set_family(self, family):
        self._add_single_line()                 # first, quietly; then the choice, which tells the bar
        self._wanted = family
        index = self.findText(family)
        if index >= 0:
            self.setCurrentIndex(index)
        elif family not in self.single_line:
            # not in the list as it is written: Qt finds the nearest font, and refills the list
            # without telling (so the single-line fonts are put back again)
            self.setCurrentFont(QFont(family))
            current = self.currentText()
            self._add_single_line()
            self.blockSignals(True)
            self.setCurrentIndex(max(0, self.findText(current)))
            self.blockSignals(False)
