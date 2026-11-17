"""
Help → About Kerfly (docs/ui-mockups/About): the logo, the name and version,
what Kerfly is, its licence and origin, the project's page; Report a problem,
Check for updates and Close in the footer.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from kerfly import __version__
from kerfly.gui import theme, widgets
from kerfly.i18n import _

LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "kerfly.png")
PROJECT_URL = "https://github.com/cyryllo/Kerfly"
ORIGIN_URL = "https://www.scorchworks.com/K40whisperer/k40whisperer.html"


class AboutDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(_("About Kerfly"))
        logo = QLabel()
        size = 4 * theme.HEIGHT_ACTION
        logo.setPixmap(QPixmap(LOGO).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignTop)
        name = QLabel("Kerfly")
        font = name.font()
        font.setPointSizeF(font.pointSizeF() * 1.6)
        font.setBold(True)
        name.setFont(font)
        version = widgets.hint(_("version %s") % __version__, wrap=False)
        title = QHBoxLayout()
        title.setSpacing(theme.SPACE_M)
        title.addWidget(name)
        title.addWidget(version, 0, Qt.AlignBottom)
        title.addStretch(1)
        what = QLabel(_("Laser cutter control software for K40 lasers with Lihuiyu M2 Nano boards: drawing, laying "
                        "out and cutting in one window."))
        what.setWordWrap(True)
        facts = QGridLayout()
        facts.setHorizontalSpacing(theme.SPACE_L)
        facts.setVerticalSpacing(theme.SPACE_S)
        for row, (key, value) in enumerate((
                (_("Licence"), _("GNU General Public License v3 or later")),
                (_("Based on"), "<a href='%s'>K40 Whisperer</a>, %s" % (ORIGIN_URL, _("by Scorch"))),
                (_("Project"), "<a href='%s'>github.com/cyryllo/Kerfly</a>" % PROJECT_URL))):
            facts.addWidget(widgets.hint(key, wrap=False), row, 0)
            label = QLabel(value)
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            facts.addWidget(label, row, 1)
        facts.setColumnStretch(1, 1)
        right = QVBoxLayout()
        right.setSpacing(theme.SPACE_L)
        right.addLayout(title)
        right.addWidget(what)
        right.addLayout(facts)
        right.addStretch(1)
        top = QHBoxLayout()
        top.setSpacing(theme.PAD_DIALOG)
        top.addWidget(logo)
        top.addLayout(right, 1)
        body = widgets.DialogBody()
        body.layout().addLayout(top)
        footer = widgets.DialogFooter(buttons=QDialogButtonBox.Close)
        footer.box.rejected.connect(self.reject)
        # the Help menu's commands, here too: they close this window first
        self.report_button = footer.add_button(_("Report a problem"),
                                               tip=window.act_report_problem.toolTip())
        self.updates_button = footer.add_button(_("Check for updates"), tip=window.act_check_updates.toolTip())
        self.report_button.clicked.connect(lambda: (self.accept(), window.act_report_problem.trigger()))
        self.updates_button.clicked.connect(lambda: (self.accept(), window.act_check_updates.trigger()))
        widgets.dialog_layout(self, body, footer)
        self.setMinimumWidth(theme.DIALOG_SMALL + 120)
