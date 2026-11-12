"""
Settings Kerfly remembers by itself, saved at once when they change (no
"Save settings as default" needed): the snap grid (on / off and its size),
snapping to other objects, "the design follows the head", and the language
(chosen in Settings, used from the next start: it was lost when the settings
were not saved as default).

They are kept in Kerfly's own window.ini (next to the material library),
not in the settings file shared with K40 Whisperer.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import os

KEYS = ("grid_mm", "grid_last_mm", "snap_objects", "follow_head", "language", "kind_buttons",
        "check_updates", "update_skip", "update_last")     # new versions: on / off, skipped, last check


def _settings():
    from PySide6.QtCore import QSettings
    from kerfly.core.materials import library_path
    return QSettings(os.path.join(os.path.dirname(library_path()), "window.ini"), QSettings.IniFormat)


def load(values):
    """Put the remembered view settings into values (the settings of the last session win)."""
    try:
        s = _settings()
        s.beginGroup("view")
        for key in KEYS:
            if s.contains(key):
                values[key] = str(s.value(key))
        s.endGroup()
    except Exception:
        pass                                     # never keep Kerfly from starting
    return values


def save(values):
    try:
        s = _settings()
        s.beginGroup("view")
        for key in KEYS:
            if key in values:
                s.setValue(key, str(values[key]))
        s.endGroup()
        s.sync()
    except Exception:
        pass
