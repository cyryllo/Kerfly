"""
Settings → Lasers… (the cog by the laser list of the Laser tab): your lasers
and each one's settings, in one window. The list on the left (New,
Duplicate, Import above it; double-click a name to change it), the selected
laser's settings on the right (board, bed, homing, programs before and after
a job, scale, power, boundary trace, rotary, USB; for a GRBL machine its
serial port), Export and Delete under them. Changes of several lasers are
kept while you go from one to another; Save writes them all (the laser in use
into the window at once), Cancel leaves them. Use this laser makes the
selected one the laser in use. The program's own settings (raster, view,
language, ...) are in Settings → Settings….

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from kerfly.core import config
from kerfly.core import profiles as profiles_core
from kerfly.gui import icons, theme, widgets
from kerfly.gui.settings_dialog import SettingsForm
from kerfly.i18n import _, ngettext


class ProfilesDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.profiles = window.profiles
        self.setWindowTitle(_("Lasers"))
        self.edits = {}                  # laser name -> its changed settings (window values), not yet saved
        self.form = None                 # the selected laser's settings
        self._form_name = None
        self.list = QListWidget()
        self.list.setToolTip(_("Your lasers"))
        self.list.currentRowChanged.connect(self._show)
        self.list.itemDoubleClicked.connect(lambda _item: self._rename())
        # the selected laser's name: an ordinary field (Enter or leaving it renames the laser)
        self.name_edit = QLineEdit()
        self.name_edit.setToolTip(_("The laser's name: type a new one and press Enter"))
        self.name_edit.editingFinished.connect(self._rename_to_field)
        self.in_use = widgets.hint("", wrap=False)
        self.buttons = {}
        for key, text, icon, tip, slot in (
                ("use", _("Use this laser"), "player-play", _("Work with this laser: its settings go into the window"),
                 self._use),
                ("new", _("New"), "plus", _("A new laser with Kerfly's default settings"), self._new),
                ("duplicate", _("Duplicate"), "copy", _("A copy of the selected laser, to change a few settings"),
                 self._duplicate),
                ("delete", _("Delete"), "trash", _("Delete the selected laser (the last one stays)"), self._delete),
                ("export", _("Export…"), "file-export", _("Save the selected laser to a file, for another computer"),
                 self._export),
                ("import", _("Import…"), "folder-open", _("Add the lasers of a file saved with Export"),
                 self._import)):
            b = QPushButton(icons.tabler(icon, theme.token("danger") if key == "delete" else None), text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            b.setFixedHeight(theme.HEIGHT_FIELD)
            self.buttons[key] = b
        # (docs/ui-mockups/Profiles) the list with New, Duplicate, Import above it on the left; the selected
        # laser on the right: its name, Rename, its settings, Export and Delete; the footer with the number of
        # lasers, Use this laser, Cancel and Save
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
        row.setSpacing(theme.SPACE_M)
        row.addWidget(widgets.icon_pixmap_label("typography", self.name_edit.toolTip()))
        row.addWidget(self.name_edit, 1)
        row.addWidget(self.in_use)
        right.addLayout(row)
        self.form_box = QVBoxLayout()
        right.addLayout(self.form_box, 1)
        row = QHBoxLayout()
        row.addWidget(self.buttons["export"])
        row.addWidget(self.buttons["delete"])
        row.addStretch(1)
        right.addLayout(row)
        top = QHBoxLayout()
        top.setSpacing(theme.PAD_DIALOG)
        top.addLayout(left, 2)
        top.addLayout(right, 5)
        body = widgets.DialogBody()
        body.layout().addLayout(top, 1)
        footer = widgets.DialogFooter(_("Save"))
        footer.box.accepted.connect(self._save_and_close)
        footer.box.rejected.connect(self.reject)
        widgets.DialogFooter.style_button(self.buttons["use"], "secondary")
        footer.layout().insertWidget(1, self.buttons["use"])
        self.count = footer.info
        widgets.dialog_layout(self, body, footer)

        self.resize(theme.DIALOG_LARGE + 240, theme.DIALOG_LARGE - 60)
        self._fill(self.profiles.current)

    def keyPressEvent(self, event):
        """Enter confirms the field it is typed in (the name: a rename), it never presses Save and closes the
        window (the field has had it first)."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    # ---------------------------------------------------------------- list
    def _fill(self, select):
        self._stash()
        self.list.blockSignals(True)
        self.list.clear()
        for name in self.profiles.names():
            item = QListWidgetItem(icons.tabler("laser"), name)
            item.setData(Qt.UserRole, name)
            if name == self.profiles.current:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(_("In use"))
            self.list.addItem(item)
        names = self.profiles.names()
        self.list.setCurrentRow(names.index(select) if select in names else 0)
        self.list.blockSignals(False)
        self._form_name = None
        self._show()

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    # ---------------------------------------------------------------- the selected laser's settings
    def _values_of(self, name):
        """The settings of a laser as the window's values (its units): changed ones, the window's for the laser
        in use, else its profile's."""
        if name in self.edits:
            return dict(self.edits[name])
        if name == self.profiles.current:
            return dict(self.window.values)
        return profiles_core.to_values(dict(self.window.values), self.profiles.get(name))

    def _stash(self):
        """Keep the changes in the form of the laser shown (until Save or Cancel)."""
        if self.form is None or self._form_name not in self.profiles.names():
            return
        new, changed = self.form.result_values()
        if changed:
            self.edits[self._form_name] = new

    def _show(self, *_args):
        name = self.selected()
        if name == self._form_name and self.form is not None:
            return
        self._stash()
        if self.form is not None:
            self.form_box.removeWidget(self.form)
            self.form.hide()
            self.form.deleteLater()
            self.form = None
        self._form_name = name
        n = len(self.profiles.items)
        self.count.setText(ngettext("%d laser", "%d lasers", n) % n)
        if name is None:
            self.name_edit.setText("")
            self.in_use.setText("")
            return
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name)
        self.name_edit.blockSignals(False)
        self.in_use.setText("(%s)" % _("in use") if name == self.profiles.current else "")
        self.form = SettingsForm(self._values_of(name), machine=True, window=self.window)
        self.form_box.addWidget(self.form)
        self.buttons["use"].setEnabled(name != self.profiles.current)
        self.buttons["delete"].setEnabled(len(self.profiles.items) > 1)

    def _save_edits(self):
        """Write the changed settings of every laser; the laser in use's go into the window. A laser that
        starts sharing another one's material library brings its own materials into it (the user's choice
        2026-11-20: always joined)."""
        self._stash()
        owners = {n: self.profiles.library_owner(n) for n in self.profiles.names()}
        for name, new in list(self.edits.items()):
            if name not in self.profiles.names():
                continue
            if name == self.profiles.current:
                changed = {k for k in new if str(new[k]) != str(self.window.values.get(k, ""))}
                if changed:
                    self.window._apply_settings(new, changed)
                    self.window._store_profile()
            else:
                self.profiles.set(name, profiles_core.from_values(new))
        self.edits.clear()
        try:
            profiles_core.save(self.profiles)
        except OSError as e:
            self.window.status(_("Could not save the lasers: %s") % e, error=True)
        from kerfly.core import materials as material_lib
        joined = []
        for name in self.profiles.names():
            own = self.profiles.get(name).get("laser_id", "")
            owner = self.profiles.library_owner(name)
            if own and owner and owner != own and owner != owners.get(name):
                try:
                    added = material_lib.join_library(material_lib.library_path(own),
                                                      material_lib.library_path(owner))
                except (OSError, ValueError) as e:
                    self.window.status(_("Could not join the material libraries: %s") % e, error=True)
                    continue
                joined.append((name, self.profiles.name_of(owner), added))
        self.window._load_materials()                    # (a library shared or not any more)
        for name, other, added in joined:
            self.window.status(_("\u201c%(laser)s\u201d now uses the material library of \u201c%(other)s\u201d; "
                                 "its own materials added to it: %(n)d") % {"laser": name, "other": other,
                                                                           "n": added})
        self._form_name = None

    def _save_and_close(self):
        self._save_edits()
        self.window.status(_("The lasers' settings were saved"))
        self.accept()

    def _changed(self, select):
        profiles_core.save(self.profiles)
        self.window._refresh_profile_box()
        self._fill(select)

    # ---------------------------------------------------------------- buttons
    def _use(self):
        name = self.selected()
        if not name:
            return
        self._save_edits()                       # its settings as changed here
        if self.window.switch_profile(name):
            self._fill(name)

    def _new(self):
        name = self.profiles.add(_("New laser"), profiles_core.from_values(config.DEFAULT_VALUES))
        self._changed(name)
        self._rename()

    def _duplicate(self):
        name = self.selected()
        if name is None:
            return
        # a copy is usually a laser of the same kind: it shares the original's material library
        source = self.profiles.get(name)
        owner = self.profiles.library_owner(name)
        copy = self.profiles.add(name, dict(source, materials_shared="1", materials_from=owner))
        self._changed(copy)
        self._rename()

    def _rename(self):
        """To the name field, its text selected (type the new name)."""
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _rename_to_field(self):
        old, new = self.selected(), self.name_edit.text().strip()
        if old is None or new == old:
            return
        self._rename_to(old, new)

    def _rename_to(self, old, new):
        self._stash()
        try:
            self.profiles.rename(old, new)
            if old in self.edits:
                self.edits[new] = self.edits.pop(old)
            if self._form_name == old:
                self._form_name = new
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
        self.edits.pop(name, None)
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
