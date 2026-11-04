"""
Break a loaded design apart: every vector path (a cut or engrave line of an
SVG, DXF or drawn text) becomes a separate polyline shape that can be edited
node by node. The raster part of a design, if any, stays as it is.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
from .design import Design

KINDS = (("engrave", "vector_engrave"), ("cut", "vector_cut"))
CLOSE_TOLERANCE = 1e-6          # inches: first and last point closer than this close the path


def vector_loops(design):
    """The vector paths of a design: list of (kind, points, closed) with points
    in design inches (y up) and kind "engrave" or "cut". A closed path does not
    repeat its first point."""
    out = []
    for kind, attr in KINDS:
        coords = getattr(design, attr).ecoords
        loop, current = None, []
        for row in coords:
            if row[2] != loop:
                if len(current) >= 2:
                    out.append(_finish(kind, current))
                loop, current = row[2], []
            p = (row[0], row[1])
            if not current or p != current[-1]:
                current.append(p)
        if len(current) >= 2:
            out.append(_finish(kind, current))
    return out


def _finish(kind, pts):
    closed = (len(pts) >= 4 and abs(pts[0][0] - pts[-1][0]) <= CLOSE_TOLERANCE
              and abs(pts[0][1] - pts[-1][1]) <= CLOSE_TOLERANCE)
    return kind, (pts[:-1] if closed else pts), closed


def raster_only(design):
    """A copy of the design with only its raster image (same bounds and
    resolution, so it stays where it was)."""
    d = Design()
    d.input_dpi = design.input_dpi
    d.raster = design.raster
    d.bounds = design.bounds
    return d


def has_vectors(design):
    return bool(design.vector_cut.ecoords or design.vector_engrave.ecoords)
