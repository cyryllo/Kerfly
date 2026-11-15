"""
Several K40 lasers plugged in: which one to connect to. "Which one?" moves the
head of the laser selected in the list a little to the right and back.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QMessageBox, QPushButton,
                               QVBoxLayout)

from kerfly.gui import icons
from kerfly.i18n import _


def identify(parent, controller, port):
    """Move the head of the laser at `port` a little; an error is shown, not raised."""
    try:
        controller.identify(port)
    except Exception as e:
        QMessageBox.warning(parent, _("USB port"), str(e))


class ChooseLaserDialog(QDialog):
    def __init__(self, ports, controller, profile_name, parent=None):
        super().__init__(parent)
        self.ports = ports
        self.setWindowTitle(_("Which laser?"))
        text = QLabel(_("%d lasers are plugged into this computer. Which one is \"%s\"? Kerfly remembers it "
                        "in this laser's settings.") % (len(ports), profile_name))
        text.setWordWrap(True)
        self.list = QListWidget()
        for p in ports:
            self.list.addItem(p.label)
        self.list.setCurrentRow(0)
        which = QPushButton(icons.tabler("arrows-horizontal"), _("Which one?"))
        which.setToolTip(_("The head of the laser selected above moves a little to the right and back"))
        which.clicked.connect(lambda: identify(self, controller, self.chosen()))
        self.which = which
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_("Connect"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(self.list)
        layout.addWidget(which)
        layout.addWidget(buttons)

    def chosen(self):
        return self.ports[max(0, self.list.currentRow())]
