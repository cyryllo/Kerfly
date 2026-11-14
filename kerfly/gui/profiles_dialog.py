"""
Settings → Lasers…: the laser profiles (one per machine): use one, add, duplicate,
rename (double click or the button), delete, export and import. The settings of
the laser in use are changed in Settings as before; they go into its profile.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from kerfly.core import config
from kerfly.core import profiles as profiles_core
from kerfly.gui import icons
from kerfly.i18n import _


class ProfilesDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.profiles = window.profiles
        self.setWindowTitle(_("Lasers"))
        self.list = QListWidget()
        self.list.setToolTip(_("Your lasers. Double-click a name to change it"))
        self.list.currentRowChanged.connect(self._show)
        self.list.itemChanged.connect(self._renamed)
        self.list.itemDoubleClicked.connect(lambda item: self.list.editItem(item))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.buttons = {}
        grid = QGridLayout()
        for n, (key, text, icon, tip, slot) in enumerate((
                ("use", _("Use"), "player-play", _("Work with this laser: its settings go into the window"),
                 self._use),
                ("new", _("New"), "plus", _("A new laser with Kerfly's default settings"), self._new),
                ("duplicate", _("Duplicate"), "copy", _("A copy of the selected laser, to change a few settings"),
                 self._duplicate),
                ("rename", _("Rename"), "typography", _("Change the name of the selected laser"), self._rename),
                ("delete", _("Delete"), "trash", _("Delete the selected laser (the last one stays)"), self._delete),
                ("export", _("Export…"), "file-export", _("Save the selected laser to a file, for another computer"),
                 self._export),
                ("import", _("Import…"), "folder-open", _("Add the lasers of a file saved with Export"),
                 self._import))):
            b = QPushButton(icons.tabler(icon, "#c62828" if key == "delete" else None), text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            self.buttons[key] = b
            grid.addWidget(b, n, 0)
        grid.setRowStretch(7, 1)
        top = QHBoxLayout()
        top.addWidget(self.list, 2)
        top.addLayout(grid)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.summary)
        hint = QLabel(_("The settings of the laser in use are changed in Settings (board, bed, power, rotary, "
                        "trace, programs before and after a job); they are kept in its profile."))
        hint.setWordWrap(True)
        hint.setObjectName("node_hint")
        layout.addWidget(hint)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.resize(620, 420)
        self._fill(self.profiles.current)

    # ---------------------------------------------------------------- list
    def _fill(self, select):
        self.list.blockSignals(True)
        self.list.clear()
        for name in self.profiles.names():
            item = QListWidgetItem(icons.tabler("laser"), name)
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            if name == self.profiles.current:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(_("In use"))
            self.list.addItem(item)
        names = self.profiles.names()
        self.list.setCurrentRow(names.index(select) if select in names else 0)
        self.list.blockSignals(False)
        self._show()

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _show(self, *_args):
        name = self.selected()
        if name is None:
            self.summary.setText("")
            return
        s = self.profiles.get(name)
        units = self.window.values.get("units", "mm")
        width, height = float(s.get("LaserXsize", 0) or 0), float(s.get("LaserYsize", 0) or 0)
        if units == "in":
            size = "%.2f × %.2f in" % (width / 25.4, height / 25.4)
        else:
            size = "%.0f × %.0f mm" % (width, height)
        parts = ["<b>%s</b>%s" % (name, " (%s)" % _("in use") if name == self.profiles.current else ""),
                 _("Board: %s") % s.get("board_name", "?"), _("Bed: %s") % size]
        if config.is_true(s.get("rotary", "0")):
            parts.append(_("Rotary attachment"))
        if config.is_true(s.get("pre_exec", "0")) or config.is_true(s.get("post_exec", "0")):
            parts.append(_("Programs before / after a job"))
        self.summary.setText("<br>".join(parts))
        self.buttons["use"].setEnabled(name != self.profiles.current)
        self.buttons["delete"].setEnabled(len(self.profiles.items) > 1)

    def _changed(self, select):
        profiles_core.save(self.profiles)
        self.window._refresh_profile_box()
        self._fill(select)

    # ---------------------------------------------------------------- buttons
    def _use(self):
        name = self.selected()
        if name and self.window.switch_profile(name):
            self._fill(name)

    def _new(self):
        name = self.profiles.add(_("New laser"), profiles_core.from_values(config.DEFAULT_VALUES))
        self._changed(name)
        self.list.editItem(self.list.currentItem())

    def _duplicate(self):
        name = self.selected()
        if name is None:
            return
        copy = self.profiles.add(name, self.profiles.get(name))
        self._changed(copy)
        self.list.editItem(self.list.currentItem())

    def _rename(self):
        item = self.list.currentItem()
        if item is not None:
            self.list.editItem(item)

    def _renamed(self, item):
        old, new = item.data(Qt.UserRole), item.text().strip()
        if new == old:
            return
        try:
            self.profiles.rename(old, new)
        except ValueError:
            self.window.status(_("A laser of this name is already there, or the name is empty."), error=True)
            self._fill(old)
            return
        self._changed(new)

    def _delete(self):
        name = self.selected()
        if name is None or len(self.profiles.items) <= 1:
            return
        if QMessageBox.question(self, _("Delete laser"), _("Delete the laser \"%s\" and its settings?") % name,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        was_current = name == self.profiles.current
        self.profiles.remove(name)
        if was_current:
            # the next one goes into the window
            first = self.profiles.current
            self.profiles.current = ""
            self.window.switch_profile(first)
        self._changed(self.profiles.current)

    def _export(self):
        name = self.selected()
        if name is None:
            return
        filename, _unused = QFileDialog.getSaveFileName(
            self, _("Export laser"), os.path.join(os.path.expanduser("~"), "%s.kerfly-laser.json" % name),
            _("Kerfly lasers") + " (*.json)")
        if not filename:
            return
        try:
            profiles_core.export_file(self.profiles, [name], filename)
        except OSError as e:
            QMessageBox.warning(self, _("Export laser"), str(e))
            return
        self.window.status(_("Laser \"%s\" saved to %s") % (name, filename))

    def _import(self):
        filename, _unused = QFileDialog.getOpenFileName(self, _("Import lasers"), os.path.expanduser("~"),
                                                        _("Kerfly lasers") + " (*.json)")
        if not filename:
            return
        try:
            added = profiles_core.import_file(self.profiles, filename)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, _("Import lasers"), _("This is not a file of Kerfly lasers: %s") % e)
            return
        self._changed(added[-1] if added else self.profiles.current)
        self.window.status(_("Lasers added: %s") % ", ".join(added))
