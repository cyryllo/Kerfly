"""
Several K40 lasers plugged in: which one to connect to. "Which one?" moves the
head of the laser selected in the list a little to the right and back.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QMessageBox, QPushButton

from kerfly.gui import icons, theme, widgets
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
        # the dialog pattern (docs/ui-mockups/WhichLaser): the question, the ports, Which one? on the footer's
        # left, Cancel and Connect
        text = widgets.label(_("%d lasers are plugged into this computer. Which one is \"%s\"? Kerfly remembers "
                               "it in this laser's settings.") % (len(ports), profile_name), "section")
        text.setWordWrap(True)
        self.list = QListWidget()
        for p in ports:
            self.list.addItem(QListWidgetItem(icons.tabler("plug-connected"), p.label))
        self.list.setCurrentRow(0)
        self.list.setToolTip(_("The USB ports with a K40 laser on them"))
        which = QPushButton(icons.tabler("arrows-horizontal"), _("Which one?"))
        which.setToolTip(_("The head of the laser selected above moves a little to the right and back"))
        which.clicked.connect(lambda: identify(self, controller, self.chosen()))
        self.which = which
        body = widgets.DialogBody()
        body.add(text)
        body.add(self.list, 1)
        footer = widgets.DialogFooter(_("Connect"))
        footer.layout().insertWidget(0, which)
        widgets.DialogFooter.style_button(which, "secondary")
        footer.connect(self)
        widgets.dialog_layout(self, body, footer)
        self.setMinimumWidth(theme.DIALOG_SMALL)

    def chosen(self):
        return self.ports[max(0, self.list.currentRow())]
