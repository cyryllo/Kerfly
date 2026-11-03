"""
Background thread for preparing jobs and sending them to the laser, so the
window stays responsive.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import traceback

from PySide6.QtCore import QThread, Signal

from kerfly.core import job, raster
from kerfly.core.laser import PauseControl


class JobWorker(QThread):
    """Runs one job.

    output_file: write an EGV file instead of sending to the laser.
    The design is modified (raster lines, path order) while running, so the
    GUI must not touch it until finished is emitted.
    """
    progress = Signal(str)
    paused = Signal()
    finished_job = Signal(bool, str)     # ok, message

    def __init__(self, design, settings, operation, laser=None, output_file=None,
                 send_options=None, parent=None):
        super().__init__(parent)
        self.design = design
        self.settings = settings
        self.operation = operation
        self.laser = laser
        self.output_file = output_file
        self.send_options = send_options or {}
        self.stop = [False]
        self.pause = PauseControl(on_paused=self.paused.emit)

    # called from the GUI thread
    def request_stop(self):
        if self.laser is not None and self.output_file is None:
            self.pause.request_pause()      # the user then chooses resume or terminate
        else:
            self.stop[0] = True

    def _progress(self, message):
        self.progress.emit(message)

    def _update_gui(self, message=None, bgcolor=None):
        if message is not None:
            self.progress.emit(message)
        if self.laser is not None and self.output_file is None:
            self.pause.poll(self.laser, self.stop)
        return True

    def run(self):
        try:
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
                self.finished_job.emit(True, "Data saved to: %s" % self.output_file)
                return
            total = 0.0
            for chunk in chunks:
                total += self.laser.send(chunk.data, power=chunk.power,
                                         update_gui=self._update_gui, stop=self.stop,
                                         **self.send_options)
            self.finished_job.emit(True, "Job finished in %d:%02d" % (total // 60, total % 60))
        except MemoryError:
            self.finished_job.emit(False, "Out of memory.")
        except Exception as e:
            message = str(e) or e.__class__.__name__
            if "stopped by user" not in message.lower():
                traceback.print_exc()
            self.finished_job.emit(False, message)
