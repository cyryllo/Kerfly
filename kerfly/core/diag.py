"""
Diagnostic log: what Kerfly and the laser did, for bug reports.

Written to kerfly.log in the user's settings folder (next to materials.json),
rotated at 1 MB with 3 old files kept. It records the start of Kerfly (versions,
system), every laser command (connect, home, moves, jobs, pause, stop), the
messages shown in the status bar, uncaught errors with their traceback, and
whatever the laser library prints.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import logging
import logging.handlers
import os
import platform
import sys
import threading
import traceback

log = logging.getLogger("kerfly")
log.addHandler(logging.NullHandler())        # quiet until setup(): no "last resort" output on stderr
LOG_NAME = "kerfly.log"
_handler = None


def log_path():
    from .materials import library_path
    return os.path.join(os.path.dirname(library_path()), LOG_NAME)


class _Tee:
    """Copy of a text stream (stdout / stderr) that also goes to the log."""

    def __init__(self, stream, level):
        self.stream = stream
        self.level = level
        self._buffer = ""

    def write(self, text):
        if self.stream is not None:
            try:
                self.stream.write(text)
            except Exception:
                pass
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                log.log(self.level, "[console] %s", line.rstrip())
        return len(text)

    def flush(self):
        if self.stream is not None:
            try:
                self.stream.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


def setup(version=""):
    """Start logging to the file. Safe to call more than once."""
    global _handler
    if _handler is not None:
        return log_path()
    path = log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                                        encoding="utf-8")
    except OSError:
        return None                                  # no log rather than no Kerfly
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

    sys.stdout = _Tee(sys.stdout, logging.INFO)
    sys.stderr = _Tee(sys.stderr, logging.WARNING)

    def excepthook(kind, value, tb):
        log.error("Uncaught error:\n%s", "".join(traceback.format_exception(kind, value, tb)).rstrip())
        sys.__excepthook__(kind, value, tb)

    def thread_excepthook(args):
        log.error("Uncaught error in thread %s:\n%s", args.thread.name if args.thread else "?",
                  "".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                     args.exc_traceback)).rstrip())

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    log.info("==== Kerfly %s started: Python %s, %s", version, platform.python_version(), platform.platform())
    return path


def read_log(max_bytes=400_000):
    """The end of the log (current file and the previous one), oldest first."""
    path = log_path()
    parts = []
    for p in (path + ".1", path):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                parts.append(f.read())
        except OSError:
            pass
    text = "".join(parts)
    return text[-max_bytes:]


def build_report(version, values=None, checks=None):
    """Text of a diagnostic report: versions, self-test lines, settings, log."""
    from . import config
    lines = ["Kerfly diagnostic report", "Kerfly %s" % version,
             "Python %s (%s)" % (platform.python_version(), platform.architecture()[0]),
             "System %s" % platform.platform(), ""]
    if checks:
        lines.append("== Checks")
        lines += ["%-4s  %-22s %s" % c for c in checks]
        lines.append("")
    lines.append("== Settings (%s)" % config.user_config_path())
    for key in sorted(values or {}):
        lines.append("%s = %s" % (key, values[key]))
    lines += ["", "== Log (%s)" % log_path(), read_log()]
    return "\n".join(lines)
