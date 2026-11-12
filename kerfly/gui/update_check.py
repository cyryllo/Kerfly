"""
Telling the user about a new Kerfly version: the check runs in the background
(the window never waits for the network), and a newer release shows a bar
above the bed with a link to its release page. Nothing is downloaded or
installed by Kerfly itself.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from kerfly.core import updates
from kerfly.gui import icons
from kerfly.i18n import _


class UpdateCheck(QThread):
    """Asks GitHub once; done(release or None, error text or "")."""
    done = Signal(object, str)

    def __init__(self, current, skipped="", parent=None, fetch=None):
        super().__init__(parent)
        self.current, self.skipped, self.fetch = current, skipped, fetch

    def run(self):
        try:
            release = updates.newer_release(self.current, self.skipped, fetch=self.fetch)
        except Exception as e:                       # no internet, GitHub not answering, ...
            self.done.emit(None, str(e) or type(e).__name__)
            return
        self.done.emit(release, "")


class UpdateBar(QFrame):
    """'Kerfly 1.3.4 is available': see the release, later, skip this version."""
    skip = Signal(str)                               # the version not to remind about

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("update_bar")
        self.release = None
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icons.tabler("cloud-download").pixmap(18, 18))
        row.addWidget(icon)
        self.text = QLabel()
        row.addWidget(self.text, 1)
        self.open_button = QPushButton(_("See the release"))
        self.open_button.setToolTip(_("Open the page of the new version: what is new and the files to download"))
        self.open_button.clicked.connect(self.open_release)
        row.addWidget(self.open_button)
        self.later_button = QPushButton(_("Later"))
        self.later_button.setToolTip(_("Hide this until the next check"))
        self.later_button.clicked.connect(self.hide)
        row.addWidget(self.later_button)
        self.skip_button = QPushButton(_("Skip this version"))
        self.skip_button.setToolTip(_("Do not remind about this version again (a later one is shown)"))
        self.skip_button.clicked.connect(self._skip)
        row.addWidget(self.skip_button)
        self.hide()

    def show_release(self, release, current):
        self.release = release
        self.text.setText(_("<b>%s is available</b> (you have %s).") % (release.name, current))
        self.show()

    def open_release(self):
        if self.release is not None:
            QDesktopServices.openUrl(QUrl(self.release.url))

    def _skip(self):
        if self.release is not None:
            self.skip.emit(self.release.version)
        self.hide()
