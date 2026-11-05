"""
Background threads for preparing jobs and sending them to the laser, so the
window stays responsive.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import traceback

from PySide6.QtCore import QThread, Signal

from kerfly.core import job, raster
from kerfly.core.laser import PauseControl
from kerfly.i18n import _


class TaskWorker(QThread):
    """Base class: progress messages, stop flag and pause handling.

    If `laser` is set, Stop pauses the board and asks (via `paused`) whether
    to resume or terminate; otherwise Stop just stops the computation.
    """
    progress = Signal(str)
    paused = Signal()
    finished_job = Signal(bool, str)     # ok, message

    def __init__(self, laser=None, send_options=None, parent=None):
        super().__init__(parent)
        self.laser = laser
        self.send_options = send_options or {}
        self.stop = [False]
        self.pause = PauseControl(on_paused=self.paused.emit)
        self.bed = None                        # (width, height) inches, for the safety check
        self.origin = None                     # bed position of the head at the job start
        self.sending = False                   # data went to the laser (the head may have moved)

    # called from the GUI thread
    def request_stop(self):
        """Stop now: the send loop stops the board (e-stop) at the next packet,
        also when the job is paused."""
        self.stop[0] = True
        self.pause.terminate()

    def request_pause(self):
        """Pause the laser (between USB packets); resume() continues."""
        if self.laser is not None:
            self.pause.request_pause()

    def resume(self):
        self.pause.resume()

    def _progress(self, message):
        self.progress.emit(message)

    def _update_gui(self, message=None, bgcolor=None):
        if message is not None:
            self.progress.emit(message)
        if self.laser is not None:
            self.pause.poll(self.laser, self.stop)
        return True

    def task(self):
        """Do the work; return the success message."""
        raise NotImplementedError

    def _check_reach(self, chunks):
        """Refuse to send a job that would move the head off the bed. Uses
        self.bed = (width, height) in inches and self.origin, the bed position
        of the head at the start (either None: not checked)."""
        if self.bed is None or self.origin is None:
            return
        for chunk in chunks:
            problem = job.reach_problem(chunk.reach, self.origin, self.bed[0], self.bed[1], self.settings)
            if problem is not None:
                side, mm = problem
                text = {"top": _("Safety check: the job would move the head %.1f mm above the top edge "
                                 "of the laser bed. Nothing was sent."),
                        "bottom": _("Safety check: the job would move the head %.1f mm below the bottom "
                                    "edge of the laser bed. Nothing was sent."),
                        "left": _("Safety check: the job would move the head %.1f mm past the left edge "
                                  "of the laser bed. Nothing was sent."),
                        "right": _("Safety check: the job would move the head %.1f mm past the right edge "
                                   "of the laser bed. Nothing was sent.")}[side]
                raise job.NoLaserData(text % mm)

    def run(self):
        try:
            self.finished_job.emit(True, self.task())
        except MemoryError:
            self.finished_job.emit(False, _("Out of memory."))
        except Exception as e:
            message = str(e) or e.__class__.__name__
            if "stopped by user" not in message.lower():
                traceback.print_exc()
            self.finished_job.emit(False, message)


def _duration(seconds):
    return "%d:%02d" % (seconds // 60, seconds % 60)


class JobWorker(TaskWorker):
    """Prepare a design job and send it to the laser or write an EGV file.

    The design is modified (raster lines, path order) while running, so the
    GUI must not touch it until finished_job is emitted.
    """

    def __init__(self, design, settings, operation, laser=None, output_file=None,
                 send_options=None, parent=None, origin=None, bed=None):
        super().__init__(laser=None if output_file else laser, send_options=send_options,
                         parent=parent)
        self.origin = origin
        self.bed = bed
        self.design = design
        self.settings = settings
        self.operation = operation
        self.output_file = output_file

    def task(self):
        op = self.operation
        if op.find(job.RASTER_ENG) > -1 or op.find(job.TRACE_ENG) > -1:
            raster.make_raster_coords(self.design, self.settings, self._progress, self.stop)
        trace = None
        if op.find(job.TRACE_ENG) > -1:
            trace = job.make_trace_path(self.design, self.settings, self._progress)
        chunks = job.build_job(self.design, self.settings, op, trace_coords=trace,
                               progress=self._progress, update_gui=self._update_gui,
                               stop=self.stop)
        if self.output_file is not None:
            if self.settings.power_per_stage:
                raise job.NoLaserData(_("Writing an EGV file is not possible with M3 power per operation "
                                        "enabled (the power settings cannot be stored in the file)."))
            with open(self.output_file, "wb") as f:
                f.write(job.egv_file_bytes(chunks[0].data))
            return _("Data saved to: %s") % self.output_file
        self._check_reach(chunks)
        self.sending = True
        total = 0.0
        for chunk in chunks:
            total += self.laser.send(chunk.data, power=chunk.power, update_gui=self._update_gui,
                                     stop=self.stop, **self.send_options)
        return _("Job finished in %s") % _duration(total)


class EgvSendWorker(TaskWorker):
    """Send the contents of an EGV file, then move the head back to the start."""

    def __init__(self, egv, passes, laser, settings, send_options=None, parent=None):
        super().__init__(laser=laser, send_options=send_options, parent=parent)
        self.egv = egv
        self.passes = 1 if egv.has_end_position else passes
        self.settings = settings

    def task(self):
        self.sending = True
        try:
            total = self.laser.send(list(self.egv.data), update_gui=self._update_gui,
                                    stop=self.stop, passes=self.passes, **self.send_options)
        finally:
            dx, dy = self.egv.return_move()
            if dx or dy:
                self.laser.rapid_move(dx, dy, self.settings, self.send_options)
        return _("EGV file sent in %s") % _duration(total)


class RasterPrepareWorker(TaskWorker):
    """Compute the raster scan lines only (for the time estimate)."""

    def __init__(self, design, settings, parent=None):
        super().__init__(parent=parent)
        self.design = design
        self.settings = settings

    def task(self):
        raster.make_raster_coords(self.design, self.settings, self._progress, self.stop)
        return _("Raster prepared")


class LayersJobWorker(TaskWorker):
    """Run all enabled layers as one job (send to the laser or write an EGV file).
    The cached layer designs are modified while running."""

    def __init__(self, elements, layers, settings, cache, laser=None, output_file=None,
                 send_options=None, parent=None, bed=None):
        super().__init__(laser=None if output_file else laser, send_options=send_options, parent=parent)
        self.bed = bed
        self.elements = list(elements)
        self.layers = [layer.copy() for layer in layers]
        self.settings = settings
        self.cache = cache
        self.output_file = output_file

    def task(self):
        from kerfly.core.layers import build_layers_job
        chunks, self.origin = build_layers_job(self.elements, self.layers, self.settings,
                                           progress=self._progress, update_gui=self._update_gui,
                                           stop=self.stop, cache=self.cache)
        if self.output_file is not None:
            if self.settings.power_per_stage:
                raise job.NoLaserData(_("Writing an EGV file is not possible with M3 power per operation "
                                        "enabled (the power settings cannot be stored in the file)."))
            with open(self.output_file, "wb") as f:
                f.write(job.egv_file_bytes(chunks[0].data))
            return _("Data saved to: %s") % self.output_file
        self._check_reach(chunks)
        self.sending = True
        total = 0.0
        for chunk in chunks:
            total += self.laser.send(chunk.data, power=chunk.power, update_gui=self._update_gui,
                                     stop=self.stop, **self.send_options)
        return _("Job finished in %s") % _duration(total)


class RasterLayersWorker(TaskWorker):
    """Prepare the raster lines of every raster layer (for the time estimate)."""

    def __init__(self, elements, layers, settings, cache, parent=None):
        super().__init__(parent=parent)
        self.elements = list(elements)
        self.layers = [layer.copy() for layer in layers]
        self.settings = settings
        self.cache = cache

    def task(self):
        from kerfly.core.layers import RASTER, compile_layer, layer_settings
        for layer in self.layers:
            if layer.kind != RASTER or not layer.enabled:
                continue
            design = self.cache.get(layer.id)
            if design is None:
                design, _origin = compile_layer(self.elements, layer, self.layers)
                if design is None:
                    continue
                self.cache[layer.id] = design
            raster.make_raster_coords(design, layer_settings(self.settings, layer), self._progress, self.stop)
        return _("Raster prepared")
