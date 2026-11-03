"""
Jog pad icons, drawn as vector graphics so they stay sharp at any size.
The style follows the K40 Whisperer icons: solid arrows for moving, dotted
guides ending in a dot for moving the head to a design corner or the centre.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

SIZE = 64          # drawing grid; the pixmap is rendered at 2x for HiDPI screens
INK = QColor("#202124")


def _canvas():
    pm = QPixmap(SIZE * 2, SIZE * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    return pm, p


def _arrow(p, angle_deg, length=26, shaft=9, head=22, head_len=14, center=(32, 32)):
    """Solid arrow through the centre, pointing at angle_deg (0 = right, 90 = up)."""
    path = QPainterPath()
    half = length
    pts = [(-half, -shaft / 2), (half - head_len, -shaft / 2), (half - head_len, -head / 2),
           (half, 0), (half - head_len, head / 2), (half - head_len, shaft / 2), (-half, shaft / 2)]
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    path.closeSubpath()
    p.save()
    p.translate(*center)
    p.rotate(-angle_deg)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(INK))
    p.drawPath(path)
    p.restore()


def _dotted_pen(width=3.0):
    pen = QPen(INK, width, Qt.CustomDashLine, Qt.RoundCap)
    pen.setDashPattern([0.1, 2.0])
    return pen


def _dot(p, x, y, r=6.0):
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(INK))
    p.drawEllipse(QPointF(x, y), r, r)


def arrow_icon(direction):
    """direction: 'up', 'down', 'left' or 'right'."""
    pm, p = _canvas()
    _arrow(p, {"right": 0, "up": 90, "left": 180, "down": 270}[direction])
    p.end()
    return QIcon(pm)


def corner_icon(corner):
    """corner: 'UL', 'UR', 'LL' or 'LR'. Dotted bracket along the two edges,
    and an arrow from the centre ending in a dot at the corner."""
    sx = -1 if corner[1] == "L" else 1
    sy = -1 if corner[0] == "U" else 1
    cx, cy = 32 + sx * 24, 32 + sy * 24       # the corner point
    pm, p = _canvas()
    # dotted bracket
    p.setPen(_dotted_pen())
    p.drawLine(QPointF(cx, cy), QPointF(cx - sx * 26, cy))
    p.drawLine(QPointF(cx, cy), QPointF(cx, cy - sy * 26))
    # diagonal arrow towards the corner, ending in the dot
    p.setPen(QPen(INK, 4.0, Qt.SolidLine, Qt.RoundCap))
    tip = QPointF(cx - sx * 9, cy - sy * 9)
    p.drawLine(QPointF(32 - sx * 10, 32 - sy * 10), tip)
    head = QPolygonF([tip + QPointF(sx * 3, sy * 3),
                      tip + QPointF(-sx * 10, 0) + QPointF(0, sy * 1),
                      tip + QPointF(sx * 1, -sy * 10)])
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(INK))
    p.drawPolygon(head)
    _dot(p, cx, cy)
    p.end()
    return QIcon(pm)


def centre_icon():
    """Dotted diagonals converging on a dot (the design centre)."""
    pm, p = _canvas()
    p.setPen(_dotted_pen())
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        p.drawLine(QPointF(32 + sx * 22, 32 + sy * 22), QPointF(32 + sx * 9, 32 + sy * 9))
    _dot(p, 32, 32, 7.0)
    p.end()
    return QIcon(pm)
