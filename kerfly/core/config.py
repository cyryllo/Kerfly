"""
Settings file (k40_whisperer.txt) reading and writing.

The format is the one used by K40 Whisperer, so settings files can be shared
with it in both directions:

    ( K40 Whisperer Settings: 0.71 )
    (k40_whisperer_set Reng_feed     100 )
    (k40_whisperer_set designfile    "/path/to/file.svg" )

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from .settings import JobSettings

IDENT = "k40_whisperer_set"
CONFIG_FILE_NAME = "k40_whisperer.txt"

BOOL, TEXT, QUOTED = "bool", "text", "quoted"

# (key, kind) in the order they are written
SETTINGS_KEYS = [
    ("include_Reng", BOOL), ("include_Veng", BOOL), ("include_Vcut", BOOL),
    ("include_Gcde", BOOL), ("include_Time", BOOL),
    ("halftone", BOOL), ("HomeUR", BOOL), ("show_power", BOOL), ("show_test", BOOL),
    ("inputCSYS", BOOL), ("advanced", BOOL), ("mirror", BOOL), ("rotate", BOOL),
    ("negate", BOOL),
    ("engraveUP", BOOL), ("init_home", BOOL), ("post_home", BOOL), ("post_beep", BOOL),
    ("post_disp", BOOL), ("post_exec", BOOL),
    ("pre_pr_crc", BOOL), ("inside_first", BOOL),
    ("comb_engrave", BOOL), ("comb_vector", BOOL), ("zoom2image", BOOL),
    ("rotary", BOOL), ("reduced_mem", BOOL), ("wait", BOOL),
    ("trace_w_laser", BOOL),
    ("max_power", TEXT), ("board_name", TEXT), ("units", TEXT),
    ("Reng_feed", TEXT), ("Veng_feed", TEXT), ("Vcut_feed", TEXT),
    ("Reng_power", TEXT), ("Veng_power", TEXT), ("Vcut_power", TEXT),
    ("Gcode_power", TEXT),   # read but never written by K40 Whisperer 0.71
    ("jog_step", TEXT),
    ("Reng_passes", TEXT), ("Veng_passes", TEXT), ("Vcut_passes", TEXT), ("Gcde_passes", TEXT),
    ("rast_step", TEXT), ("ht_size", TEXT),
    ("LaserXsize", TEXT), ("LaserYsize", TEXT),
    ("LaserXscale", TEXT), ("LaserYscale", TEXT), ("LaserRscale", TEXT), ("rapid_feed", TEXT),
    ("gotoX", TEXT), ("gotoY", TEXT),
    ("bezier_M1", TEXT), ("bezier_M2", TEXT), ("bezier_weight", TEXT),
    ("trace_gap", TEXT), ("trace_speed", TEXT), ("Trace_power", TEXT),
    ("test_time", TEXT), ("test_power", TEXT),
    ("t_timeout", TEXT), ("n_timeouts", TEXT),
    ("ink_timeout", TEXT),
    ("designfile", QUOTED), ("inkscape_path", QUOTED), ("batch_path", QUOTED),
]
SETTINGS_KINDS = dict(SETTINGS_KEYS)

# Default values, as set by K40 Whisperer 0.71 on startup.
DEFAULT_VALUES = {
    "include_Reng": "1", "include_Veng": "1", "include_Vcut": "1", "include_Gcde": "1",
    "include_Time": "0", "halftone": "1", "HomeUR": "0", "show_power": "1", "show_test": "1",
    "inputCSYS": "0", "advanced": "0", "mirror": "0", "rotate": "0", "negate": "0",
    "engraveUP": "0", "init_home": "1", "post_home": "0", "post_beep": "0", "post_disp": "0",
    "post_exec": "0", "pre_pr_crc": "1", "inside_first": "1", "comb_engrave": "0",
    "comb_vector": "0", "zoom2image": "0", "rotary": "0", "reduced_mem": "0", "wait": "1",
    "trace_w_laser": "0",
    "max_power": "30", "board_name": "LASER-M2", "units": "mm",
    "Reng_feed": "100", "Veng_feed": "20", "Vcut_feed": "10",
    "Reng_power": "0.5", "Veng_power": "0.5", "Vcut_power": "0.5", "Gcode_power": "0.5",
    "jog_step": "10.0",
    "Reng_passes": "1", "Veng_passes": "1", "Vcut_passes": "1", "Gcde_passes": "1",
    "rast_step": "0.002", "ht_size": "500",
    "LaserXsize": "325", "LaserYsize": "220",
    "LaserXscale": "1.000", "LaserYscale": "1.000", "LaserRscale": "1.000", "rapid_feed": "0.0",
    "gotoX": "0.0", "gotoY": "0.0",
    "bezier_M1": "2.5", "bezier_M2": "0.50", "bezier_weight": "3.5",
    "trace_gap": "0", "trace_speed": "50", "Trace_power": "0.5",
    "test_time": "250", "test_power": "0.5",
    "t_timeout": "200", "n_timeouts": "30", "ink_timeout": "3",
    "designfile": "", "inkscape_path": "", "batch_path": "",
}

BOARD_NAMES = ["LASER-M2", "LASER-M1", "LASER-M", "LASER-B2", "LASER-B1", "LASER-B",
               "LASER-A", "LASER-M3"]


def user_config_path():
    """Settings file in the user's home directory (shared with K40 Whisperer)."""
    import os
    return os.path.join(os.path.expanduser("~"), CONFIG_FILE_NAME)


def load_user_settings():
    """Defaults updated with the user's settings file, if there is one."""
    import os
    values = dict(DEFAULT_VALUES)
    path = user_config_path()
    if os.path.isfile(path):
        try:
            values.update(read_settings_file(path))
        except OSError:
            pass
    return values


def is_true(value):
    """Truth value of a bool setting given as bool, int or string."""
    if isinstance(value, str):
        try:
            return float(value) != 0
        except ValueError:
            return value.strip().lower() == "true"
    return bool(value)


def bed_size_inches(values):
    """(width, height) of the laser bed in inches."""
    scale = 1.0 if values.get("units") == "in" else 25.4
    return float(values["LaserXsize"]) / scale, float(values["LaserYsize"]) / scale


def parse_settings(lines):
    """Parse settings lines into {key: value string}. Unknown keys and
    malformed lines are ignored (as in K40 Whisperer)."""
    values = {}
    for line in lines:
        pos = line.find(IDENT)
        if pos < 0:
            continue
        rest = line[pos + len(IDENT):].strip()
        parts = rest.split(None, 1)
        if len(parts) < 2:
            continue
        key, tail = parts
        kind = SETTINGS_KINDS.get(key)
        if kind is None:
            continue
        if kind == QUOTED:
            q = tail.split('"')
            if len(q) < 3:
                continue
            values[key] = q[1]
        else:
            values[key] = tail.split()[0]
    return values


def read_settings_file(filename):
    with open(filename, "r") as fin:
        return parse_settings(fin)


def format_settings(values, version):
    """Settings file lines for {key: value}. Bool values may be given as
    bool/int/str; keys missing from values are skipped."""
    out = ["( K40 Whisperer Settings: %s )" % version,
           "( by Scorch - 2019 )",
           "(=========================================================)"]
    for key, kind in SETTINGS_KEYS:
        if key not in values:
            continue
        val = values[key]
        if kind == BOOL:
            val = int(val) if not isinstance(val, str) else int(float(val))
            out.append("(%s %-13s %s )" % (IDENT, key, val))
        elif kind == QUOTED:
            out.append('(%s %-13s "%s" )' % (IDENT, key, val))
        else:
            out.append("(%s %-13s %s )" % (IDENT, key, val))
    out.append("(=========================================================)")
    return out


def write_settings_file(filename, values, version):
    lines = format_settings(values, version)
    with open(filename, "w") as fout:
        for line in lines:
            fout.write(line + "\n")


def _flag(value):
    return is_true(value)


def job_settings_from_values(values, power_per_stage=False):
    """Build JobSettings from settings-file style values (missing keys keep
    their defaults). Numbers are converted the way K40 Whisperer converted
    them at the point of use. Raises ValueError naming an invalid setting."""
    s = JobSettings(power_per_stage=power_per_stage)

    def num(key):
        try:
            return float(values[key])
        except ValueError:
            raise ValueError("Invalid value for setting '%s': %r" % (key, values[key]))

    def put(attr, key, conv):
        if key in values:
            setattr(s, attr, conv(key))

    put("board_name", "board_name", lambda k: values[k])
    put("units", "units", lambda k: values[k])
    for attr, key in [("home_upper_right", "HomeUR"), ("input_csys", "inputCSYS"),
                      ("mirror", "mirror"), ("rotate", "rotate"), ("rotary", "rotary"),
                      ("inside_first", "inside_first"), ("engrave_up", "engraveUP"),
                      ("negate", "negate"), ("halftone", "halftone")]:
        put(attr, key, lambda k: _flag(values[k]))
    put("trace_with_laser", "trace_w_laser", lambda k: _flag(values[k]))
    for attr, key in [("max_power", "max_power"), ("x_scale", "LaserXscale"),
                      ("y_scale", "LaserYscale"), ("rotary_scale", "LaserRscale"),
                      ("rapid_feed", "rapid_feed"),
                      ("raster_feed", "Reng_feed"), ("raster_power", "Reng_power"),
                      ("raster_step", "rast_step"), ("halftone_dpi", "ht_size"),
                      ("bezier_m1", "bezier_M1"), ("bezier_m2", "bezier_M2"),
                      ("bezier_weight", "bezier_weight"),
                      ("vengrave_feed", "Veng_feed"), ("vengrave_power", "Veng_power"),
                      ("vcut_feed", "Vcut_feed"), ("vcut_power", "Vcut_power"),
                      ("gcode_power", "Gcode_power"),
                      ("trace_feed", "trace_speed"), ("trace_gap", "trace_gap"),
                      ("trace_power", "Trace_power")]:
        put(attr, key, num)
    for attr, key in [("raster_passes", "Reng_passes"), ("vengrave_passes", "Veng_passes"),
                      ("vcut_passes", "Vcut_passes"), ("gcode_passes", "Gcde_passes")]:
        put(attr, key, lambda k: int(num(k)))
    return s


def convert_units(values, new_units):
    """Return values with lengths and speeds converted to new_units ('mm' or 'in'),
    rounded as K40 Whisperer does. Speeds are mm/s in mm mode, in/min in inch mode."""
    if new_units == "in":
        factor, vfactor = 1 / 25.4, 60.0 / 25.4
    elif new_units == "mm":
        factor, vfactor = 25.4, 25.4 / 60.0
    else:
        raise ValueError(new_units)
    out = dict(values)

    def scale(key, fmt, f):
        try:
            out[key] = fmt % (float(values[key]) * f)
        except (KeyError, ValueError):
            out[key] = ""
    for key in ("LaserXsize", "LaserYsize"):
        scale(key, "%.2f", factor)
    for key in ("jog_step", "gotoX", "gotoY"):
        scale(key, "%.3f", factor)
    for key in ("Reng_feed", "Veng_feed", "Vcut_feed", "trace_speed", "rapid_feed"):
        scale(key, "%.1f", vfactor)
    out["units"] = new_units
    return out
