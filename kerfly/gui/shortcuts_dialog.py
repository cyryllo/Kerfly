"""
Help → Keyboard shortcuts: every command with a key (read from the menus and the
drawing tools, so new commands show up by themselves) and the mouse actions.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLineEdit, QMenu, QTreeWidget,
                               QTreeWidgetItem)

from kerfly.gui import icons, theme, widgets
from kerfly.i18n import N_, _

# what the mouse does and keys that belong to no command
MOUSE = [
    (N_("Select several elements"), N_("Drag a frame around them, or Ctrl+click")),
    (N_("Move the selection"), N_("Drag it, or the arrow keys (1 mm or one grid step; with Shift 10 times more)")),
    (N_("Snap to nothing for a moment"), N_("Hold Alt while drawing, dragging or moving a node")),
    (N_("Square, circle, 45° lines"), N_("Hold Shift while drawing")),
    (N_("Polyline and pen: finish"), N_("Click the first point to close; double-click or Enter for an open line; "
                                         "Backspace removes the last point; Esc cancels")),
    (N_("Mirror the selection, as in Inkscape"), N_("H horizontally, V vertically (with the bed in focus)")),
    (N_("Edit the nodes of an element"), N_("Double-click it")),
    (N_("Node editing keys"), N_("I insert, D delete, L line, C curve, O smooth, S symmetric, Z close / open, "
                                  "B break")),
    (N_("Zoom"), N_("Mouse wheel")),
    (N_("Pan the view"), N_("Drag with the middle or the right mouse button")),
    (N_("Right click"), N_("A menu: on an element its commands, on the empty bed Move the head here")),
]


def _plain(text):
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").rstrip("…").rstrip(".").strip()


def _keys(action):
    return ",  ".join(s.toString(QKeySequence.NativeText) for s in action.shortcuts() if not s.isEmpty())


def _menu_rows(menu, prefix=""):
    rows = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        sub = action.menu()
        if isinstance(sub, QMenu):
            rows += _menu_rows(sub, prefix + _plain(action.text()) + " → ")
        elif _keys(action):
            rows.append((prefix + _plain(action.text()), _keys(action)))
    return rows


def sections(window):
    """[(section title, [(command, keys)])] of the window."""
    result = []
    for action in window.menuBar().actions():
        menu = action.menu()
        if isinstance(menu, QMenu):
            rows = _menu_rows(menu)
            if rows:
                result.append((_plain(action.text()), rows))
    tools = [(_plain(a.toolTip().split("\n")[0] or a.text()), _keys(a))
             for a in getattr(window, "tool_actions", {}).values() if _keys(a)]
    if tools:
        result.append((_("Drawing tools"), tools))
    result.append((_("Mouse and other keys"), [(_(what), _(how)) for what, how in MOUSE]))
    return result


class ShortcutsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(_("Keyboard shortcuts"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(_("Find a command or a key"))
        self.filter.setClearButtonEnabled(True)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([_("Command"), _("Keys / mouse")])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setWordWrap(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        for title, rows in sections(window):
            top = QTreeWidgetItem([title])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            top.setFirstColumnSpanned(False)
            self.tree.addTopLevelItem(top)
            for command, keys in rows:
                item = QTreeWidgetItem([command, keys])
                item.setToolTip(1, keys)
                top.addChild(item)
            top.setExpanded(True)
        self.filter.textChanged.connect(self._filter)
        self.filter.setToolTip(_("Shows only the commands whose name or keys have this text"))
        self.filter.addAction(icons.tabler("search"), QLineEdit.LeadingPosition)
        # the dialog pattern (docs/ui-mockups/Shortcuts): the search, the list, Close with a note beside it
        body = widgets.DialogBody()
        body.add(self.filter)
        body.add(self.tree, 1)
        footer = widgets.DialogFooter(buttons=QDialogButtonBox.Close)
        footer.info.setText(_("The shortcuts of the menus and tools appear here by themselves"))
        footer.box.rejected.connect(self.close)
        widgets.dialog_layout(self, body, footer)
        self.resize(theme.DIALOG_LARGE, theme.DIALOG_LARGE - 60)

    def _filter(self, text):
        text = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            shown = 0
            for j in range(top.childCount()):
                child = top.child(j)
                hit = not text or text in child.text(0).lower() or text in child.text(1).lower() \
                    or text in top.text(0).lower()
                child.setHidden(not hit)
                shown += hit
            top.setHidden(shown == 0)

    def rows(self):
        """[(section, command, keys)] shown (for the tests)."""
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if not child.isHidden() and not top.isHidden():
                    out.append((top.text(0), child.text(0), child.text(1)))
        return out
