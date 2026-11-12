"""
The mouse wheel changes a number field or a drop-down list only after it was
clicked (it has the keyboard focus). Passing over a field while scrolling a
panel scrolls the panel and leaves the value alone: before, scrolling down to
Start on a small screen changed the speeds of the layers on the way (a user's
report 2026-11-12).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox

GUARDED = (QAbstractSpinBox, QComboBox)


def _guarded(obj):
    """The number field or list a wheel event over obj would change (obj or
    its parent, e.g. the text part of a number field), or None."""
    if isinstance(obj, GUARDED):
        return obj
    parent = obj.parent() if isinstance(obj, QObject) else None
    return parent if isinstance(parent, GUARDED) else None


class WheelGuard(QObject):
    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Polish and isinstance(obj, GUARDED):
            # the wheel must not give the focus (Qt's default for these widgets)
            if obj.focusPolicy() == Qt.WheelFocus:
                obj.setFocusPolicy(Qt.StrongFocus)
        elif kind == QEvent.Wheel:
            field = _guarded(obj)
            if field is not None and not field.hasFocus():
                # not clicked: the panel underneath scrolls instead
                area = _scroll_area(field)
                if area is None:
                    event.ignore()                   # goes on to the parent (real wheel events)
                    return True
                viewport = area.viewport()
                pos = viewport.mapFromGlobal(event.globalPosition().toPoint())
                QApplication.sendEvent(viewport, QWheelEvent(
                    QPointF(pos), event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                    event.buttons(), event.modifiers(), event.phase(), event.inverted()))
                event.accept()
                return True
        return False


def _scroll_area(widget):
    w = widget.parentWidget()
    while w is not None:
        if isinstance(w, QAbstractScrollArea):
            return w
        w = w.parentWidget()
    return None


_guard = None


def install(app=None):
    """Install the guard once for the whole program."""
    global _guard
    app = app or QApplication.instance()
    if app is None or _guard is not None:
        return _guard
    _guard = WheelGuard(app)
    app.installEventFilter(_guard)
    return _guard
