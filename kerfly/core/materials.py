"""
Material library: saved cut / outline engrave / raster engrave settings for
materials such as "Plywood 3 mm". Choosing a material sets every layer of the
matching kind.

Stored as JSON in the user's settings folder:
    Linux:   ~/.config/kerfly/materials.json   (or $XDG_CONFIG_HOME)
    Windows: %APPDATA%\\Kerfly\\materials.json
Speeds are stored in mm/s whatever units the user works in.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import json
import os
import sys
from dataclasses import asdict, dataclass, field

from kerfly.i18n import N_, _

KINDS = ("cut", "engrave", "raster")
FILE_NAME = "materials.json"


@dataclass
class OperationSettings:
    speed: float = 10.0       # mm/s
    passes: int = 1
    power: float = 0.5        # fraction of max power (M3 boards)
    kerf: float = 0.0         # mm, cut: width of the cut (kerf compensation of the cut layer)


@dataclass
class Material:
    name: str
    thickness_mm: float = 0.0
    notes: str = ""
    settings: dict = field(default_factory=dict)     # kind -> OperationSettings

    def get(self, kind):
        return self.settings.get(kind)


def _material(name, thickness, notes, cut=None, engrave=None, raster=None):
    s = {}
    for kind, values in (("cut", cut), ("engrave", engrave), ("raster", raster)):
        if values is not None:
            s[kind] = OperationSettings(*values)
    return Material(name, thickness, notes, s)


EXAMPLE_NOTE = N_("Example starting values for a typical 40 W K40; test on a scrap piece first.")


def example_materials():
    """A few starting points (names in the user's language); every laser and
    material batch differs."""
    note = _(EXAMPLE_NOTE)
    return [
        _material(_("Plywood 3 mm"), 3, note, cut=(8, 1, 0.6), engrave=(25, 1, 0.3), raster=(150, 1, 0.3)),
        _material(_("Plywood 4 mm"), 4, note, cut=(6, 2, 0.65), engrave=(25, 1, 0.3), raster=(150, 1, 0.3)),
        _material(_("Acrylic 3 mm"), 3, note, cut=(6, 1, 0.6), engrave=(30, 1, 0.25), raster=(200, 1, 0.25)),
        _material(_("Cardboard 2 mm"), 2, note, cut=(15, 1, 0.4), engrave=(40, 1, 0.2), raster=(250, 1, 0.2)),
        _material(_("Leather 2 mm"), 2, note, cut=(10, 1, 0.5), engrave=(30, 1, 0.25), raster=(200, 1, 0.25)),
    ]


def library_path():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Kerfly", FILE_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "kerfly", FILE_NAME)


def to_json(materials):
    return json.dumps({"version": 1, "materials": [
        {"name": m.name, "thickness_mm": m.thickness_mm, "notes": m.notes,
         "settings": {k: asdict(v) for k, v in m.settings.items()}} for m in materials]},
        indent=2, ensure_ascii=False)


def from_json(text):
    data = json.loads(text)
    out = []
    for m in data.get("materials", []):
        settings = {}
        for kind, v in (m.get("settings") or {}).items():
            if kind in KINDS:
                settings[kind] = OperationSettings(float(v.get("speed", 10)), int(v.get("passes", 1)),
                                                   float(v.get("power", 0.5)), float(v.get("kerf", 0.0)))
        out.append(Material(str(m.get("name", "?")), float(m.get("thickness_mm", 0) or 0),
                            str(m.get("notes", "")), settings))
    return out


def load_library(path=None):
    """Materials from the user's library; the examples if there is none yet."""
    path = path or library_path()
    if not os.path.isfile(path):
        return example_materials()
    with open(path, encoding="utf-8") as f:
        return from_json(f.read())


def save_library(materials, path=None):
    path = path or library_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(to_json(materials))
    os.replace(tmp, path)
    return path


def merge_materials(existing, imported):
    """Add imported materials; a material with the same name (ignoring case)
    is replaced. Returns (merged list, number added, number replaced)."""
    merged = list(existing)
    by_name = {m.name.strip().lower(): i for i, m in enumerate(merged)}
    added = replaced = 0
    for m in imported:
        key = m.name.strip().lower()
        if key in by_name:
            merged[by_name[key]] = m
            replaced += 1
        else:
            by_name[key] = len(merged)
            merged.append(m)
            added += 1
    return merged, added, replaced


def export_library(materials, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_json(materials))


def import_library(path):
    with open(path, encoding="utf-8") as f:
        return from_json(f.read())
