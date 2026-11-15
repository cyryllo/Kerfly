"""
The element list of the Design tab as a tree: groups (and groups inside them,
e.g. the sheets of a generated box) as rows that open and close, with the
elements inside. A group's tick takes all its elements in or out of the job;
picking a group's row selects that group alone (a sheet of a box can be moved
on its own).

The rows of the elements keep the element list's numbering (item(n) is the
row of element n, row(item) its number, -1 for a group's row).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

ELEMENT = Qt.UserRole            # the element's number
GROUP = Qt.UserRole + 1          # a group's path


class Row(QTreeWidgetItem):
    """A row; its text and tick also as the element list's rows had them (no column)."""

    def text(self, column=0):
        return super().text(column)

    def checkState(self, column=0):
        return super().checkState(column)

    def setCheckState(self, *args):
        if len(args) == 1:
            super().setCheckState(0, args[0])
        else:
            super().setCheckState(*args)


class ElementTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.header().setStretchLastSection(True)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)    # as wide as the list: no side scrolling
        self._rows = []                          # the rows of the elements, in the elements' order
        self._groups = {}                        # path -> the group's row
        self.closed = set()                      # paths of the groups shut by the user
        self.opened = set()                      # paths of the groups opened by the user (shut at first)
        self._filling = False
        self.itemCollapsed.connect(self._collapsed)
        self.itemExpanded.connect(self._expanded)

    def _collapsed(self, item):
        if not self._filling:
            self.closed.add(item.data(0, GROUP))
            self.opened.discard(item.data(0, GROUP))

    def _expanded(self, item):
        if not self._filling:
            self.opened.add(item.data(0, GROUP))
            self.closed.discard(item.data(0, GROUP))

    # ---- the element list's ways ---------------------------------------------
    def count(self):
        return len(self._rows)

    def item(self, row):
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row(self, item):
        if item is None:
            return -1
        n = item.data(0, ELEMENT)
        return n if isinstance(n, int) else -1

    def group_of(self, item):
        """The path of a group's row ("" for an element's row)."""
        return (item.data(0, GROUP) or "") if item is not None else ""

    def group_item(self, path):
        return self._groups.get(path)

    def setCurrentRow(self, row, flags=None):
        item = self.item(row)
        if item is not None:
            if flags is None:
                self.setCurrentItem(item)
            else:
                self.setCurrentItem(item, 0, flags)

    # ---- filling ------------------------------------------------------------------
    def fill(self, rows):
        """rows: [(group paths of the element, outermost first, [(path, name)]), (icon, text, tooltip, ticked)]."""
        self._filling = True
        self.clear()
        self._rows, self._groups = [], {}
        for n, (groups, (icon, text, tip, ticked)) in enumerate(rows):
            parent = None
            for path, name in groups:
                node = self._groups.get(path)
                if node is None:
                    node = Row([name])
                    node.setData(0, GROUP, path)
                    node.setFlags((node.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsAutoTristate)
                    if parent is None:
                        self.addTopLevelItem(node)
                    else:
                        parent.addChild(node)
                    self._groups[path] = node
                parent = node
            item = Row([text])
            item.setData(0, ELEMENT, n)
            if icon is not None:
                item.setIcon(0, icon)
            if tip:
                item.setToolTip(0, tip)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if ticked else Qt.Unchecked)
            if parent is None:
                self.addTopLevelItem(item)
            else:
                parent.addChild(item)
            self._rows.append(item)
        for path, node in self._groups.items():
            name = node.text(0)
            node.setCheckState(0, self._tick_of(node))
            node.setText(0, "%s (%d)" % (name, len(self.members(path))))
            # a part (a group named as its shapes, e.g. an outline and its slots) starts shut
            children = [node.child(i) for i in range(node.childCount())]
            one_part = all(self.row(c) >= 0 and c.text(0).startswith(name) for c in children)
            node.setExpanded(path in self.opened or (path not in self.closed and not one_part))
        self._filling = False

    def members(self, path):
        """The numbers of the elements in a group (also in the groups inside it)."""
        node = self._groups.get(path)
        out = []
        stack = [node] if node is not None else []
        while stack:
            it = stack.pop()
            for i in range(it.childCount()):
                child = it.child(i)
                if self.row(child) >= 0:
                    out.append(self.row(child))
                else:
                    stack.append(child)
        return sorted(out)

    def _tick_of(self, node):
        states = {self._rows[n].checkState(0) for n in self.members(node.data(0, GROUP))}
        if states == {Qt.Checked}:
            return Qt.Checked
        if states == {Qt.Unchecked}:
            return Qt.Unchecked
        return Qt.PartiallyChecked
