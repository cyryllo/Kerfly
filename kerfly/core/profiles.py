"""
Laser profiles: the settings of each machine (board, bed, home corner, scale,
power, rotary, trace, programs before / after a job) under a name, for example
"K40 in the workshop". One laser is used at a time: choosing a profile puts its
settings into the window; changing a machine setting changes the profile in use.

Saved in profiles.json next to the material library (the user's settings folder).
Lengths and speeds are kept in millimetres (mm/s) whatever units the window shows.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import json
import os

from kerfly.core import config

FILE_NAME = "profiles.json"
FORMAT = "kerfly-laser-profiles"

# the settings of the machine; everything else (language, theme, grid, units, ...) is the program's
MACHINE_KEYS = (
    "board_name", "LaserXsize", "LaserYsize", "HomeUR", "init_home", "post_home_xy", "post_home", "post_beep",
    "post_disp", "pre_exec", "pre_batch_path", "post_exec", "batch_path", "LaserXscale", "LaserYscale",
    "show_power", "max_power", "rotary", "LaserRscale", "rapid_feed", "trace_w_laser", "trace_rect", "trace_gap",
    "trace_speed", "Trace_power", "test_time", "test_power", "t_timeout", "n_timeouts", "pre_pr_crc", "wait",
    "usb_port", "gcode_origin", "gcode_s_max", "gcode_overscan", "machine", "grbl_port", "grbl_baud", "grbl_home",
    "grbl_jog",
)


def path():
    from kerfly.core.materials import library_path
    return os.path.join(os.path.dirname(library_path()), FILE_NAME)


def from_values(values):
    """The machine settings of the window's values, in millimetres."""
    v = dict(values)
    if v.get("units") == "in":
        v = config.convert_units(v, "mm")
    return {k: str(v[k]) for k in MACHINE_KEYS if k in v}


def to_values(values, settings):
    """values with a profile's settings put in, converted to the units of values."""
    merged = dict(values)
    units = merged.get("units", "mm")
    if units == "in":
        merged = config.convert_units(merged, "mm")       # the profile is in mm
    merged.update({k: str(settings[k]) for k in MACHINE_KEYS if k in settings})
    merged["units"] = "mm"
    if units == "in":
        merged = config.convert_units(merged, "in")
    out = dict(values)
    out.update({k: merged[k] for k in MACHINE_KEYS if k in merged})
    return out


class Profiles:
    """[(name, settings)] and the name in use."""

    def __init__(self, items=None, current=""):
        self.items = list(items or [])
        self.current = current if any(n == current for n, _s in self.items) else \
            (self.items[0][0] if self.items else "")

    def names(self):
        return [n for n, _s in self.items]

    def get(self, name):
        for n, s in self.items:
            if n == name:
                return s
        raise KeyError(name)

    def set(self, name, settings):
        for i, (n, _s) in enumerate(self.items):
            if n == name:
                self.items[i] = (n, dict(settings))
                return
        self.items.append((name, dict(settings)))

    def add(self, name, settings):
        name = self.free_name(name)
        self.items.append((name, dict(settings)))
        return name

    def rename(self, old, new):
        new = new.strip()
        if not new or (new != old and new in self.names()):
            raise ValueError(new)
        self.items = [(new if n == old else n, s) for n, s in self.items]
        if self.current == old:
            self.current = new

    def remove(self, name):
        if len(self.items) <= 1:
            raise ValueError("the last profile stays")
        self.items = [(n, s) for n, s in self.items if n != name]
        if self.current == name:
            self.current = self.items[0][0]

    def free_name(self, name):
        name = name.strip() or "Laser"
        if name not in self.names():
            return name
        n = 2
        while "%s (%d)" % (name, n) in self.names():
            n += 1
        return "%s (%d)" % (name, n)

    def to_json(self, only=None):
        items = [(n, s) for n, s in self.items if only is None or n in only]
        return {"format": FORMAT, "version": 1, "current": self.current,
                "profiles": [{"name": n, "settings": s} for n, s in items]}

    @classmethod
    def from_json(cls, data):
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError("not a Kerfly laser profile file")
        items = []
        for p in data.get("profiles", []):
            name = str(p.get("name", "")).strip()
            settings = p.get("settings", {})
            if name and isinstance(settings, dict):
                items.append((name, {k: str(v) for k, v in settings.items() if k in MACHINE_KEYS}))
        return cls(items, str(data.get("current", "")))


def load():
    """The saved profiles, or None when there is no file yet."""
    try:
        with open(path(), encoding="utf-8") as f:
            return Profiles.from_json(json.load(f))
    except (OSError, ValueError):
        return None


def save(profiles):
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profiles.to_json(), f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def load_or_create(values, first_name):
    """The saved profiles; the first time one profile made of the current settings."""
    profiles = load()
    if profiles is None or not profiles.items:
        profiles = Profiles([(first_name, from_values(values))], first_name)
        try:
            save(profiles)
        except OSError:
            pass
    return profiles


def apply_current(values, first_name):
    """At start: the settings of the profile in use put into values (in place)."""
    profiles = load_or_create(values, first_name)
    values.update(to_values(values, profiles.get(profiles.current)))
    return profiles


def export_file(profiles, names, filename):
    data = profiles.to_json(only=set(names))
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def import_file(profiles, filename):
    """Adds the profiles of a file (a name taken gets a number); returns their names."""
    with open(filename, encoding="utf-8") as f:
        other = Profiles.from_json(json.load(f))
    return [profiles.add(n, s) for n, s in other.items]
