"""
Job simulation window: plays the laser head's moves on the bed view, in the
order the job runs them (kerfly.core.simulate).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QGraphicsEllipseItem, QGraphicsItem, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QVBoxLayout)

from kerfly.core.simulate import RASTER_ROW_MM, timeline, total_seconds
from kerfly.gui import icons
from kerfly.i18n import _

SPEEDS = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
WATCH_SECONDS = 30.0             # the automatic speed plays the whole job in about this time
# red where the laser is on (whatever the layer), grey for moves with the laser off; a raster
# row is drawn only over its dark parts and one row wide, so what is engraved turns red
BURN = QColor("#e53935")
COLORS = {"raster": BURN, "engrave": BURN, "cut": BURN, "gcode": BURN,
          "move": QColor("#9e9e9e")}


def _pen(color, width=1.6, style=Qt.SolidLine):
    p = QPen(color, width, style)
    p.setCosmetic(True)
    return p


def _clock(seconds):
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


class SimulationDialog(QDialog):
    def __init__(self, window, steps):
        super().__init__(window)
        self.setWindowTitle(_("Job simulation"))
        self.view = window.preview
        self.steps = steps
        self.total = total_seconds(steps)
        self.ends = []
        t = 0.0
        for s in steps:
            t += s.seconds
            self.ends.append(t)
        self.time = 0.0
        self.items = []
        self.burn_items = {}

        self.play = QPushButton()
        self.play.setIcon(icons.tabler("player-play"))
        self.play.setToolTip(_("Play / pause"))
        self.play.clicked.connect(self.toggle)
        self.speed = QComboBox()
        for n in SPEEDS:
            self.speed.addItem("%d×" % n, n)
        # automatic speed: the whole job in about half a minute
        wanted = self.total / WATCH_SECONDS if self.total else 1
        self.speed.setCurrentIndex(min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - wanted)))
        self.speed.setToolTip(_("Playback speed (1× = real time)"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(lambda v: self.seek(self.total * v / 1000.0))
        self.label = QLabel()
        self.next_layer = QPushButton()
        self.next_layer.setIcon(icons.tabler("player-track-next"))
        self.next_layer.setToolTip(_("Jump to the next layer"))
        self.next_layer.clicked.connect(self.skip_layer)
        row = QHBoxLayout()
        row.addWidget(self.play)
        row.addWidget(self.next_layer)
        row.addWidget(self.slider, 1)
        row.addWidget(self.speed)
        v = QVBoxLayout(self)
        v.addLayout(row)
        v.addWidget(self.label)
        hint = QLabel(_("Red: what the laser has burnt so far (raster engraving one line every 0.2 mm). "
                        "Grey dashed lines: moves with the laser off."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7280;")
        v.addWidget(hint)
        self.resize(460, self.sizeHint().height())

        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.seek(0.0)

    # ---- playback ------------------------------------------------------------------
    def toggle(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play.setIcon(icons.tabler("player-play"))
        else:
            if self.time >= self.total:
                self.seek(0.0)
            self.timer.start()
            self.play.setIcon(icons.tabler("player-pause"))

    def skip_layer(self):
        """Go to the start of the next layer (or the end)."""
        current = None
        for st, end in zip(self.steps, self.ends):
            if end > self.time:
                current = (st.kind, st.layer)
                break
        t = 0.0
        for st, end in zip(self.steps, self.ends):
            if end > self.time and (st.kind, st.layer) != current:
                self.seek(t)
                return
            t = end
        self.seek(self.total)

    def _tick(self):
        self.seek(min(self.total, self.time + 0.033 * self.speed.currentData()))
        if self.time >= self.total:
            self.toggle()

    def seek(self, t):
        self.time = max(0.0, min(t, self.total))
        self._draw()
        if not self.slider.isSliderDown():
            self.slider.setValue(int(1000 * self.time / self.total) if self.total else 0)
        self.label.setText(_("%s of %s") % (_clock(self.time), _clock(self.total)))

    # ---- drawing on the bed view ------------------------------------------------------
    def _clear(self):
        scene = self.view.scene()
        for it in self.items:
            try:
                if it.scene() is scene:
                    scene.removeItem(it)
            except RuntimeError:
                pass                              # the bed view was redrawn: already gone
        self.items = []

    def _scene_point(self, x, y):
        if self.view.home_ur:
            x = self.view.bed_w_mm - x
        return QPointF(x, y)

    def _draw(self):
        self._clear()
        scene = self.view.scene()
        paths = {}
        head = None
        start = 0.0
        for s, end in zip(self.steps, self.ends):
            if start >= self.time:
                break
            f = 1.0 if end <= self.time or s.seconds <= 0 else (self.time - start) / s.seconds
            a = self._scene_point(s.x0, s.y0)
            b = self._scene_point(s.x0 + (s.x1 - s.x0) * f, s.y0 + (s.y1 - s.y0) * f)
            key = s.kind if s.burn else "move"
            qp = paths.setdefault(key, QPainterPath())
            if s.burn and s.runs:                 # a raster row: only where it is dark
                for r0, r1 in s.runs:
                    if r0 >= f:
                        break
                    r1 = min(r1, f)
                    qp.moveTo(self._scene_point(s.x0 + (s.x1 - s.x0) * r0, s.y0 + (s.y1 - s.y0) * r0))
                    qp.lineTo(self._scene_point(s.x0 + (s.x1 - s.x0) * r1, s.y0 + (s.y1 - s.y0) * r1))
            else:
                qp.moveTo(a)
                qp.lineTo(b)
            head = b
            start = end
        for key, qp in paths.items():
            if key == "raster":
                # as wide as the row it stands for (in mm on the bed), so the rows touch but do not pile up
                pen = QPen(COLORS["raster"], RASTER_ROW_MM, Qt.SolidLine, Qt.FlatCap)
            else:
                pen = _pen(COLORS.get(key, BURN), 1.0 if key == "move" else 2.5,
                           Qt.DashLine if key == "move" else Qt.SolidLine)
            item = scene.addPath(qp, pen)
            item.setZValue(60)
            self.items.append(item)
        if head is None and self.steps:
            head = self._scene_point(self.steps[0].x0, self.steps[0].y0)
        if head is not None:
            dot = QGraphicsEllipseItem(-6, -6, 12, 12)
            dot.setPen(_pen(QColor("#f57c00"), 2))
            dot.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            dot.setPos(head)
            dot.setZValue(61)
            scene.addItem(dot)
            self.items.append(dot)

    def done(self, result):
        self.timer.stop()
        self._clear()
        super().done(result)


def simulation_steps(window):
    """Steps of the current job of a main window (or [] with nothing to do)."""
    settings = window.job_settings()
    units = window.values.get("units", "mm")
    hx, hy = window.head
    return timeline(window.elements, window.layers, settings, units, start=(hx * 25.4, -hy * 25.4))
