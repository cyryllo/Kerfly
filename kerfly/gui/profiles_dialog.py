"""
Settings → Lasers…: the laser profiles (one per machine): use one, add, duplicate,
rename (double click or the button), delete, export and import. The settings of
the laser in use are changed in Settings as before; they go into its profile.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from kerfly.core import config
from kerfly.core import profiles as profiles_core
from kerfly.gui import icons, theme, widgets
from kerfly.i18n import _, ngettext


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
        self.title = widgets.section_title("")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.buttons = {}
        for key, text, icon, tip, slot in (
                ("use", _("Use this laser"), "player-play", _("Work with this laser: its settings go into the window"),
                 self._use),
                ("new", _("New"), "plus", _("A new laser with Kerfly's default settings"), self._new),
                ("duplicate", _("Duplicate"), "copy", _("A copy of the selected laser, to change a few settings"),
                 self._duplicate),
                ("rename", _("Rename"), "typography", _("Change the name of the selected laser"), self._rename),
                ("delete", _("Delete"), "trash", _("Delete the selected laser (the last one stays)"), self._delete),
                ("export", _("Export…"), "file-export", _("Save the selected laser to a file, for another computer"),
                 self._export),
                ("import", _("Import…"), "folder-open", _("Add the lasers of a file saved with Export"),
                 self._import)):
            b = QPushButton(icons.tabler(icon, theme.token("danger") if key == "delete" else None), text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            if key != "use":
                b.setFixedHeight(theme.HEIGHT_FIELD)
            self.buttons[key] = b
        # the dialog pattern (docs/ui-mockups/Profiles): the list with New, Duplicate, Import above it on the
        # left; the selected laser on the right (its name, Rename, what it has, Export and Delete); the footer
        # with the number of lasers, Close and Use this laser
        left = QVBoxLayout()
        left.setSpacing(theme.SPACE_M)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_S)
        for key in ("new", "duplicate", "import"):
            row.addWidget(self.buttons[key])
        row.addStretch(1)
        left.addLayout(row)
        left.addWidget(self.list, 1)
        right = QVBoxLayout()
        right.setSpacing(theme.SPACE_M)
        row = QHBoxLayout()
        row.addWidget(self.title, 1)
        row.addWidget(self.buttons["rename"])
        right.addLayout(row)
        right.addWidget(self.summary)
        right.addWidget(widgets.hint(_("The settings of the laser in use are changed in Settings (board, bed, power, "
                                       "rotary, trace, programs before and after a job); they are kept in its "
                                       "profile.")))
        right.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.buttons["export"])
        row.addWidget(self.buttons["delete"])
        row.addStretch(1)
        right.addLayout(row)
        top = QHBoxLayout()
        top.setSpacing(theme.PAD_DIALOG)
        top.addLayout(left, 1)
        top.addLayout(right, 1)
        body = widgets.DialogBody()
        body.layout().addLayout(top, 1)
        footer = widgets.DialogFooter(buttons=QDialogButtonBox.Close)
        footer.box.rejected.connect(self.reject)
        widgets.DialogFooter.style_button(self.buttons["use"], "primary")
        footer.layout().addWidget(self.buttons["use"])          # the action, last (after Close)
        self.count = footer.info
        widgets.dialog_layout(self, body, footer)
        self.resize(theme.DIALOG_LARGE, theme.DIALOG_SMALL + 20)
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
            self.title.setText("")
            return
        s = self.profiles.get(name)
        units = self.window.values.get("units", "mm")
        width, height = float(s.get("LaserXsize", 0) or 0), float(s.get("LaserYsize", 0) or 0)
        if units == "in":
            size = "%.2f × %.2f in" % (width / 25.4, height / 25.4)
        else:
            size = "%.0f × %.0f mm" % (width, height)
        self.title.setText(name + (" (%s)" % _("in use") if name == self.profiles.current else ""))
        rows = [(_("Board"), s.get("board_name", "?")), (_("Bed"), size),
                (_("Rotary attachment"), _("yes") if config.is_true(s.get("rotary", "0")) else _("no"))]
        if config.is_true(s.get("pre_exec", "0")) or config.is_true(s.get("post_exec", "0")):
            rows.append((_("Programs"), _("before / after a job")))
        hint = theme.token("hint")
        self.summary.setText("<table cellspacing='4'>%s</table>" % "".join(
            "<tr><td style='color:%s; padding-right:12px'>%s</td><td>%s</td></tr>" % (hint, k, v) for k, v in rows))
        n = len(self.profiles.items)
        self.count.setText(ngettext("%d laser", "%d lasers", n) % n)
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
        if widgets.ask(self, _("Delete laser"), _("Delete the laser \"%s\" and its settings?") % name,
                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No, names={QMessageBox.Yes: _("Delete laser")},
                       danger=True) != QMessageBox.Yes:
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
