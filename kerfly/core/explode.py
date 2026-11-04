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


# ---- splitting a raster into its separate parts --------------------------------------
def raster_pieces(image, dpi, cell_mm=0.25, threshold=250):
    """Separate parts of a picture (areas of non-white pixels that do not touch,
    looked at on a grid of cell_mm). Returns [(box, piece)] where box is
    (left, top, right, bottom) in pixels and piece the part's pixels on white
    (neighbours inside its box are left out)."""
    from PIL import Image
    gray = image.convert("L")
    w, h = gray.size
    cell = max(1, int(round(cell_mm / 25.4 * dpi)))
    gw, gh = (w + cell - 1) // cell, (h + cell - 1) // cell
    # a cell is "ink" when any pixel in it is darker than the threshold
    small = gray.point(lambda v: 255 if v < threshold else 0).resize((gw, gh), Image.BOX)
    ink = small.load()
    label = [[0] * gw for _ in range(gh)]
    pieces = []
    for cy in range(gh):
        for cx in range(gw):
            if ink[cx, cy] == 0 or label[cy][cx]:
                continue
            n = len(pieces) + 1
            stack = [(cx, cy)]
            label[cy][cx] = n
            cells = []
            while stack:
                x, y = stack.pop()
                cells.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1),
                               (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)):
                    if 0 <= nx < gw and 0 <= ny < gh and ink[nx, ny] and not label[ny][nx]:
                        label[ny][nx] = n
                        stack.append((nx, ny))
            pieces.append(cells)
    out = []
    for n, cells in enumerate(pieces, 1):
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        box = (min(xs) * cell, min(ys) * cell, min(w, (max(xs) + 1) * cell), min(h, (max(ys) + 1) * cell))
        from PIL import ImageDraw
        mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
        draw = ImageDraw.Draw(mask)
        for x, y in cells:
            draw.rectangle((x * cell - box[0], y * cell - box[1],
                            min((x + 1) * cell, w) - box[0] - 1, min((y + 1) * cell, h) - box[1] - 1), fill=255)
        piece = Image.new("L", mask.size, 255)
        piece.paste(gray.crop(box), (0, 0), mask)
        out.append((box, piece))
    return out
