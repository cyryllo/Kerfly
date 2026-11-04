"""
Kerfly project files (.kerfly).

A project is a zip archive:
    project.json        layers, elements (placement, layer assignment, drawn
                        shapes) and loading options
    files/<n>_<name>    copies of the source files (SVG, DXF, images, G-code),
                        so a project can be moved to another computer as one file

Loading options (image resolution, DXF units, SVG scale) are stored so opening
a project never asks those questions again.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import json
import os
import tempfile
import zipfile
from dataclasses import asdict, fields

from .layers import Layer
from .shapes import ShapeSpec

FORMAT_VERSION = 1
EXTENSION = ".kerfly"


class ProjectError(Exception):
    pass


def _layer_to_dict(layer):
    return {"id": layer.id, "kind": layer.kind, "name": layer.name, "color": layer.color,
            "speed": layer.speed, "passes": layer.passes, "power": layer.power, "enabled": layer.enabled}


def _shape_to_dict(spec):
    d = asdict(spec)
    d["text_outlines"] = [[list(p) for p in poly] for poly in spec.text_outlines]
    d["points"] = [list(p) for p in spec.points]
    return d


def _shape_from_dict(d):
    names = {f.name for f in fields(ShapeSpec)}
    spec = ShapeSpec(**{k: v for k, v in d.items() if k in names})
    spec.text_outlines = [[tuple(p) for p in poly] for poly in (d.get("text_outlines") or [])]
    spec.points = [tuple(p) for p in (d.get("points") or [])]
    return spec


def save_project(path, elements, layers, info=None):
    """Write elements and layers to a .kerfly file. info: extra dict saved as is
    (e.g. chosen material). Source files are copied into the archive."""
    data = {"format": "kerfly-project", "version": FORMAT_VERSION, "info": info or {},
            "layers": [_layer_to_dict(layer) for layer in layers], "elements": []}
    files = []                                   # (archive name, source path)
    for i, e in enumerate(elements):
        item = {"name": e.name, "x": e.x, "y": e.y, "scale_x": e.scale_x, "scale_y": e.scale_y,
                "rotation": e.rotation, "visible": e.visible,
                "layers": {k: v for k, v in e.layers.items()}}
        if e.shape is not None:
            item["shape"] = _shape_to_dict(e.shape)
        else:
            if not e.source_file or not os.path.isfile(e.source_file):
                raise ProjectError("Source file of '%s' not found: %s" % (e.name, e.source_file))
            arc = "files/%d_%s" % (i, os.path.basename(e.source_file))
            files.append((arc, e.source_file))
            item["file"] = arc
            item["original_path"] = e.source_file
            item["load_options"] = dict(e.load_options)
        data["elements"].append(item)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(data, indent=2, ensure_ascii=False))
        for arc, src in files:
            z.write(src, arc)
    os.replace(tmp, path)


def read_project(path):
    """Read a .kerfly file. Returns (data, folder) where the embedded source
    files have been extracted into folder (kept for the session); element
    entries get "path" pointing at their extracted file."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ProjectError("Not a Kerfly project: %s" % e)
    with z:
        try:
            data = json.loads(z.read("project.json").decode("utf-8"))
        except (KeyError, ValueError) as e:
            raise ProjectError("Not a Kerfly project: %s" % e)
        if data.get("format") != "kerfly-project":
            raise ProjectError("Not a Kerfly project.")
        if int(data.get("version", 0)) > FORMAT_VERSION:
            raise ProjectError("This project was saved by a newer Kerfly version.")
        folder = tempfile.mkdtemp(prefix="kerfly_project_")
        for item in data.get("elements", []):
            arc = item.get("file")
            if arc:
                if arc.startswith("/") or ".." in arc.split("/"):
                    raise ProjectError("Invalid file name in project: %s" % arc)
                z.extract(arc, folder)
                item["path"] = os.path.join(folder, *arc.split("/"))
    return data, folder


def layers_from_data(data):
    """Layers of a project, with the saved ids mapped to new Layer objects:
    returns (layers, {saved id: layer})."""
    layers, by_id = [], {}
    for d in data.get("layers", []):
        layer = Layer(d["kind"], name=d.get("name", ""), color=d.get("color", "#000000"),
                      speed=float(d.get("speed", 10)), passes=int(d.get("passes", 1)),
                      power=float(d.get("power", 0.5)), enabled=bool(d.get("enabled", True)))
        layers.append(layer)
        by_id[d.get("id")] = layer
    return layers, by_id


def shape_from_item(item):
    return _shape_from_dict(item["shape"]) if "shape" in item else None
