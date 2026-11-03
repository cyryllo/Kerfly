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

    # called from the GUI thread
    def request_stop(self):
        if self.laser is not None:
            self.pause.request_pause()      # the user then chooses resume or terminate
        else:
            self.stop[0] = True

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

    def run(self):
        try:
            self.finished_job.emit(True, self.task())
        except MemoryError:
            self.finished_job.emit(False, "Out of memory.")
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
                 send_options=None, parent=None):
        super().__init__(laser=None if output_file else laser, send_options=send_options,
                         parent=parent)
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
                raise job.NoLaserData("Writing EGV file not supported with M3 power settings enabled")
            with open(self.output_file, "wb") as f:
                f.write(job.egv_file_bytes(chunks[0].data))
            return "Data saved to: %s" % self.output_file
        total = 0.0
        for chunk in chunks:
            total += self.laser.send(chunk.data, power=chunk.power, update_gui=self._update_gui,
                                     stop=self.stop, **self.send_options)
        return "Job finished in %s" % _duration(total)


class EgvSendWorker(TaskWorker):
    """Send the contents of an EGV file, then move the head back to the start."""

    def __init__(self, egv, passes, laser, settings, send_options=None, parent=None):
        super().__init__(laser=laser, send_options=send_options, parent=parent)
        self.egv = egv
        self.passes = 1 if egv.has_end_position else passes
        self.settings = settings

    def task(self):
        try:
            total = self.laser.send(list(self.egv.data), update_gui=self._update_gui,
                                    stop=self.stop, passes=self.passes, **self.send_options)
        finally:
            dx, dy = self.egv.return_move()
            if dx or dy:
                self.laser.rapid_move(dx, dy, self.settings, self.send_options)
        return "EGV file sent in %s" % _duration(total)


class RasterPrepareWorker(TaskWorker):
    """Compute the raster scan lines only (for the time estimate)."""

    def __init__(self, design, settings, parent=None):
        super().__init__(parent=parent)
        self.design = design
        self.settings = settings

    def task(self):
        raster.make_raster_coords(self.design, self.settings, self._progress, self.stop)
        return "Raster prepared"
