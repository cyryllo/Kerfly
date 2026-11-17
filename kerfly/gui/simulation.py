"""
Job simulation window (docs/ui-mockups/Simulation): a window of its own with
its own preview of the bed, playing the laser head's moves in the order the
job runs them (kerfly.core.simulate). The whole job is drawn grey (to do),
what the laser has burnt so far red, the head as an orange ring.

Above the preview: Play / Pause, the time slider, the time, the speed, Next
layer; under it the legend, the current layer and Close. When the design
changes while it is open, it works the job out again after a short pause and
keeps its place in time (paused, a note says so); New and Open close it.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGraphicsEllipseItem, QGraphicsItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget)

from kerfly.core.simulate import RASTER_ROW_MM, timeline, total_seconds
from kerfly.gui import icons, theme, widgets
from kerfly.i18n import C_, _

SPEEDS = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
WATCH_SECONDS = 30.0             # the automatic speed plays the whole job in about this time
REFRESH_MS = 300                 # a changed design is worked out again after this pause
NOTE_MS = 4000                   # how long "the design changed" stays in the footer
# red where the laser is on (whatever the layer), grey for moves with the laser off; a raster
# row is drawn only over its dark parts and one row wide, so what is engraved turns red
BURN = theme.canvas("burn")
COLORS = {"raster": BURN, "engrave": BURN, "cut": BURN, "gcode": BURN,
          "move": theme.canvas("move")}
TODO = theme.canvas("outline")   # the job still to do


def _pen(color, width=1.6, style=Qt.SolidLine):
    p = QPen(color, width, style)
    p.setCosmetic(True)
    return p


def _clock(seconds):
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def _signature(steps):
    """What the job is, to tell whether a change of the design changed it."""
    return tuple((round(s.x0, 4), round(s.y0, 4), round(s.x1, 4), round(s.y1, 4), s.burn, s.kind, s.layer,
                  round(s.seconds, 6)) for s in steps)


class SimulationView(QGraphicsView):
    """The simulation's own preview: fitted to the bed when resized."""

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setBackgroundBrush(QBrush(theme.canvas("background")))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.bed = QRectF()

    def fit(self):
        if not self.bed.isEmpty():
            self.fitInView(self.bed.adjusted(-5, -5, 5, 5), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()


class SimulationDialog(QDialog):
    def __init__(self, window, steps):
        super().__init__(window)
        self.setWindowTitle(_("Job simulation"))
        self.setWindowFlag(Qt.Window, True)           # a window of its own (beside the main one)
        self.window_ = window
        self.home_ur = window.preview.home_ur
        self.bed_w_mm = window.preview.bed_w_mm
        self.items = []
        self.time = 0.0

        self.scene = QGraphicsScene(self)
        self.view = SimulationView(self.scene)
        # the bar over the preview: Play, the slider, the time, the speed, Next layer
        self.play = QPushButton(icons.tabler("player-play", theme.token("action_ink")), _("Play"))
        self.play.setToolTip(_("Play / pause"))
        self.play.clicked.connect(self.toggle)
        widgets.DialogFooter.style_button(self.play, "primary")
        self.play.setFixedHeight(theme.HEIGHT_FIELD)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setToolTip(_("Where the job is: drag to go there"))
        self.slider.sliderMoved.connect(lambda v: self.seek(self.total * v / 1000.0))
        self.label = QLabel()
        self.speed = QComboBox()
        for n in SPEEDS:
            self.speed.addItem("%d×" % n, n)
        self.speed.setToolTip(_("Playback speed (1× = real time)"))
        self.next_layer = QPushButton(icons.tabler("player-track-next"), _("Next layer"))
        self.next_layer.setToolTip(_("Jump to the next layer"))
        self.next_layer.clicked.connect(self.skip_layer)
        self.next_layer.setFixedHeight(theme.HEIGHT_FIELD)
        bar = widgets.PreviewBar()
        bar.add(self.play)
        bar.layout().addWidget(self.slider, 1)
        bar.add(self.label)
        bar.add_separator()
        bar.add(widgets.caption("player-track-next", _("Speed"), self.speed.toolTip()))
        bar.add(self.speed)
        bar.add(self.next_layer)
        # the footer: the legend and the current layer, Close
        footer = widgets.DialogFooter(buttons=QDialogButtonBox.Close)
        footer.box.rejected.connect(self.close)
        self.info = footer.info
        legend = QWidget()
        lh = QHBoxLayout(legend)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(theme.SPACE_L)
        for color, text in ((BURN, _("burnt")), (TODO, _("to do"))):
            swatch = QLabel()
            swatch.setFixedSize(theme.ICON_SMALL, 3)
            swatch.setStyleSheet("background: %s;" % color.name())     # the canvas colour it stands for
            lh.addWidget(swatch)
            lh.addWidget(widgets.hint(text, wrap=False))
        footer.layout().insertWidget(0, legend)
        layout = widgets.dialog_layout(self, self.view, footer, bar)
        layout.setStretchFactor(self.view, 1)
        self.resize(theme.DIALOG_LARGE + 140, theme.DIALOG_LARGE - 160)

        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        # a changed design: worked out again after a pause (kept at its place in time)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(REFRESH_MS)
        self.refresh_timer.timeout.connect(self.refresh)
        self.note_timer = QTimer(self)
        self.note_timer.setSingleShot(True)
        self.note_timer.setInterval(NOTE_MS)
        self.note_timer.timeout.connect(self._show_layer)
        self._note = ""
        self.set_steps(steps)
        # automatic speed: the whole job in about half a minute
        wanted = self.total / WATCH_SECONDS if self.total else 1
        self.speed.setCurrentIndex(min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - wanted)))
        self.seek(0.0)

    def set_steps(self, steps):
        """The job to play: its steps; the bed and the whole job drawn grey."""
        self.steps = steps
        self.total = total_seconds(steps)
        self.ends = []
        t = 0.0
        for s in steps:
            t += s.seconds
            self.ends.append(t)
        self._signature = _signature(steps)
        self.items = []
        self.scene.clear()
        from kerfly.core import config
        bed_w, bed_h = (v * 25.4 for v in config.bed_size_inches(self.window_.values))
        bed = QRectF(0, 0, bed_w, bed_h)
        self.scene.addRect(bed, _pen(theme.canvas("bed_border"), 1), QBrush(theme.canvas("bed")))
        todo = QPainterPath()
        for s in steps:
            if s.burn:
                todo.moveTo(self._scene_point(s.x0, s.y0))
                todo.lineTo(self._scene_point(s.x1, s.y1))
        item = self.scene.addPath(todo, _pen(TODO, 1.2))
        item.setZValue(1)
        self.scene.setSceneRect(bed.adjusted(-20, -20, 20, 20))
        self.view.bed = bed
        self.view.fit()

    # ---- the design changed in the main window ----------------------------------------
    def design_changed(self):
        """Called by the main window on every change: work the job out again after a pause."""
        self.refresh_timer.start()

    def refresh(self):
        """The job again from the window, at the same place in time (paused); a note in the footer."""
        try:
            steps = simulation_steps(self.window_)
        except ValueError:
            return
        if _signature(steps) == self._signature:
            return                                     # the job is the same (e.g. a selection changed)
        share = self.time / self.total if self.total else 0.0
        if self.timer.isActive():
            self.toggle()
        self.set_steps(steps)
        self.seek(share * self.total)
        self._note = _("The design changed: the simulation was worked out again")
        self.note_timer.start()
        self._show_layer()

    # ---- playback ------------------------------------------------------------------
    def toggle(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play.setIcon(icons.tabler("player-play", theme.token("action_ink")))
            self.play.setText(_("Play"))
        else:
            if self.time >= self.total:
                self.seek(0.0)
            self._note = ""
            self.timer.start()
            self.play.setIcon(icons.tabler("player-pause", theme.token("action_ink")))
            self.play.setText(C_("job", "Pause"))

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
        self._show_layer()

    def _show_layer(self):
        """The footer: a note (the design changed) for a moment, else the layer being lasered now."""
        if self._note and self.note_timer.isActive():
            self.info.setText(self._note)
            return
        self._note = ""
        layer = None
        for st, end in zip(self.steps, self.ends):
            if end >= self.time and st.burn:
                layer = st.layer
                break
        self.info.setText(_("Layer: %s") % layer if layer else "")

    # ---- drawing on the own preview -----------------------------------------------------
    def _clear(self):
        scene = self.scene
        for it in self.items:
            try:
                if it.scene() is scene:
                    scene.removeItem(it)
            except RuntimeError:
                pass                              # the bed view was redrawn: already gone
        self.items = []

    def _scene_point(self, x, y):
        if self.home_ur:
            x = self.bed_w_mm - x
        return QPointF(x, y)

    def _draw(self):
        self._clear()
        scene = self.scene
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
            dot.setPen(_pen(theme.canvas("head"), 2))
            dot.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            dot.setPos(head)
            dot.setZValue(61)
            scene.addItem(dot)
            self.items.append(dot)

    def done(self, result):
        self.timer.stop()
        self.refresh_timer.stop()
        super().done(result)

    def closeEvent(self, event):
        self.timer.stop()
        self.refresh_timer.stop()
        super().closeEvent(event)


def simulation_steps(window):
    """Steps of the current job of a main window (or [] with nothing to do)."""
    settings = window.job_settings()
    units = window.values.get("units", "mm")
    hx, hy = window.head
    return timeline(window.elements, window.layers, settings, units, start=(hx * 25.4, -hy * 25.4))
