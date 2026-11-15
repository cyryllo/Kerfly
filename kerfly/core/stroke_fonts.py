"""
Single-line (stroke) fonts for engraving: every letter is a few lines the laser
runs along once, instead of an outline to fill (faster, finer, like a pen
plotter). The fonts come with Kerfly (kerfly/fonts/single_line: the Hershey
fonts and the EMS fonts of Evil Mad Scientist Laboratories, SVG fonts), so no
Inkscape is needed.

The fonts have no Polish letters with ogonek, kreska, kropka or ł; those are put
together from the plain letter and the mark (taken from ć, İ and i where the
font has them, drawn otherwise).

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import math
import os
import re
import xml.etree.ElementTree as ET

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "single_line")
LINE_SPACING = 1.25            # lines of text, in em
ITALIC_SLANT = 0.2             # italic: x moved by this much per unit of height

_families = None               # {family: file}
_loaded = {}                   # family: Font


class Font:
    def __init__(self, family, units, ascent, descent, glyphs, default_advance):
        self.family = family
        self.units = units                     # units per em
        self.ascent = ascent
        self.descent = descent
        self.glyphs = glyphs                   # char: (advance, [polyline (x, y up)])
        self.default_advance = default_advance


def families():
    """Names of the single-line fonts, as shown in the font list."""
    global _families
    if _families is None:
        _families = {}
        try:
            names = sorted(os.listdir(FONT_DIR))
        except OSError:
            names = []
        for name in names:
            if name.lower().endswith(".svg"):
                path = os.path.join(FONT_DIR, name)
                try:
                    with open(path, encoding="utf-8") as f:
                        head = f.read(4000)
                except OSError:
                    continue
                m = re.search(r'font-family="([^"]+)"', head)
                if m:
                    _families[m.group(1)] = path
    return sorted(_families, key=lambda n: (not n.startswith("Hershey"), n.lower()))


def is_stroke(family):
    return family in families() if family else False


# ------------------------------------------------------------------ reading
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TOKEN = re.compile(r"[MLCZmlcz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _parse_path(d):
    """SVG path data with M, L, C, Z (absolute, as in these fonts) -> polylines."""
    tokens = _TOKEN.findall(d or "")
    polys, current, cmd, i = [], [], None, 0
    pos = (0.0, 0.0)
    start = pos

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t.upper()
            i += 1
            if cmd == "Z":
                if current:
                    current.append(start)
                    polys.append(current)
                current = []
                pos = start
                continue
        if cmd == "M":
            if len(current) > 1:
                polys.append(current)
            pos = (num(), num())
            start = pos
            current = [pos]
            cmd = "L"                           # more pairs after M are lines
        elif cmd == "L":
            pos = (num(), num())
            current.append(pos)
        elif cmd == "C":
            c1, c2, end = (num(), num()), (num(), num()), (num(), num())
            p0 = pos
            for k in range(1, 9):
                t_ = k / 8.0
                a = (1 - t_) ** 3
                b = 3 * (1 - t_) ** 2 * t_
                c = 3 * (1 - t_) * t_ ** 2
                e = t_ ** 3
                current.append((a * p0[0] + b * c1[0] + c * c2[0] + e * end[0],
                                a * p0[1] + b * c1[1] + c * c2[1] + e * end[1]))
            pos = end
        else:
            i += 1                              # anything else: skipped
    if len(current) > 1:
        polys.append(current)
    return polys


def _load(family):
    font = _loaded.get(family)
    if font is not None:
        return font
    families()
    path = _families.get(family)
    if path is None:
        raise KeyError(family)
    root = ET.parse(path).getroot()
    ns = {"s": "http://www.w3.org/2000/svg"}
    font_el = root.find(".//s:font", ns)
    face = root.find(".//s:font-face", ns)
    default_adv = float(font_el.get("horiz-adv-x", "500"))
    units = float(face.get("units-per-em", "1000"))
    ascent = float(face.get("ascent", "800"))
    descent = float(face.get("descent", "-200"))
    glyphs = {}
    for g in root.findall(".//s:glyph", ns):
        ch = g.get("unicode")
        if not ch or len(ch) != 1:
            continue
        glyphs[ch] = (float(g.get("horiz-adv-x", default_adv)), _parse_path(g.get("d")))
    font = Font(family, units, ascent, descent, glyphs, default_adv)
    _add_polish(font)
    _loaded[family] = font
    return font


# ------------------------------------------------------------------ Polish letters
def _bbox(polys):
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)


def _mark(glyphs, marked, plain):
    """The lines of `marked` that `plain` does not have (the accent of ć over c)."""
    if marked not in glyphs or plain not in glyphs:
        return None
    key = lambda p: tuple((round(x, 1), round(y, 1)) for x, y in p)   # noqa: E731
    base = {key(p) for p in glyphs[plain][1]}
    extra = [p for p in glyphs[marked][1] if key(p) not in base]
    return extra or None


def _centred_over(mark, base_polys, lift=0.0):
    """The mark moved over the middle of the base letter (and up by `lift`)."""
    mx0, my0, mx1, _my1 = _bbox(mark)
    bx0, _by0, bx1, by1 = _bbox(base_polys)
    dx = (bx0 + bx1) / 2.0 - (mx0 + mx1) / 2.0
    dy = max(0.0, by1 + lift - my0) if lift else 0.0
    return [[(x + dx, y + dy) for x, y in p] for p in mark]


def _add_polish(font):
    g = font.glyphs
    h = font.units
    acute_lower = _mark(g, "ć", "c")
    acute_upper = _mark(g, "Ć", "C")
    dot_upper = _mark(g, "İ", "I")
    dot_lower = _mark(g, "i", "ı")

    def drawn_acute(base):
        _x0, _y0, _x1, y1 = _bbox(base)
        cx = (_x0 + _x1) / 2.0
        return [[(cx - 0.04 * h, y1 + 0.08 * h), (cx + 0.07 * h, y1 + 0.2 * h)]]

    def drawn_dot(base):
        _x0, _y0, _x1, y1 = _bbox(base)
        cx, cy, r = (_x0 + _x1) / 2.0, y1 + 0.13 * h, 0.025 * h
        return [[(cx + r * math.cos(a * math.pi / 4), cy + r * math.sin(a * math.pi / 4)) for a in range(9)]]

    def ogonek(base):
        x0, _y0, x1, _y1 = _bbox(base)
        r = x1 - 0.12 * (x1 - x0)
        return [[(r, 0.0), (r - 0.06 * h, -0.07 * h), (r - 0.06 * h, -0.14 * h), (r - 0.02 * h, -0.18 * h),
                 (r + 0.04 * h, -0.19 * h)]]

    def slash(base, stem_x):
        _x0, y0, _x1, y1 = _bbox(base)
        mid = y0 + (y1 - y0) * 0.45
        return [[(stem_x - 0.12 * h, mid - 0.08 * h), (stem_x + 0.16 * h, mid + 0.1 * h)]]

    def make(ch, base_ch, extra):
        if ch in g or base_ch not in g:
            return
        adv, polys = g[base_ch]
        g[ch] = (adv, [list(p) for p in polys] + extra(polys))

    for ch, base in (("ń", "n"), ("ś", "s"), ("ź", "z")):
        make(ch, base, lambda p: _centred_over(acute_lower, p) if acute_lower else drawn_acute(p))
    for ch, base in (("Ń", "N"), ("Ś", "S"), ("Ź", "Z")):
        make(ch, base, lambda p: _centred_over(acute_upper, p) if acute_upper else drawn_acute(p))
    make("ż", "z", lambda p: _centred_over(dot_lower, p) if dot_lower else drawn_dot(p))
    make("Ż", "Z", lambda p: _centred_over(dot_upper, p) if dot_upper else drawn_dot(p))
    for ch, base in (("ą", "a"), ("ę", "e"), ("Ą", "A"), ("Ę", "E")):
        make(ch, base, ogonek)
    make("ł", "l", lambda p: slash(p, (_bbox(p)[0] + _bbox(p)[2]) / 2.0))
    make("Ł", "L", lambda p: slash(p, _bbox(p)[0] + 0.03 * h))
    for ch, base in (("ć", "c"), ("Ć", "C"), ("ó", "o"), ("Ó", "O")):
        make(ch, base, drawn_acute)


# ------------------------------------------------------------------ laying out
def _glyph(font, ch):
    if ch in font.glyphs:
        return font.glyphs[ch]
    if ch.isspace():
        return font.glyphs.get(" ", (font.default_advance, []))
    return font.glyphs.get("?", (font.default_advance, []))


def advance(family, ch, size_mm, spacing_mm=0.0):
    font = _load(family)
    return _glyph(font, ch)[0] * size_mm / font.units + spacing_mm


def line_width(family, text, size_mm, spacing_mm=0.0):
    font = _load(family)
    k = size_mm / font.units
    widths = [_glyph(font, ch)[0] * k for ch in text]
    return sum(widths) + spacing_mm * max(0, len(text) - 1)


def glyph_lines(family, ch, size_mm, italic=False):
    """The lines of one letter (mm, y down, baseline at y=0, starting at x=0)."""
    font = _load(family)
    k = size_mm / font.units
    _adv, polys = _glyph(font, ch)
    out = []
    for p in polys:
        out.append([((x + (y * ITALIC_SLANT if italic else 0.0)) * k, -y * k) for x, y in p])
    return out


def text_lines(text, family, size_mm, italic=False, spacing_mm=0.0):
    """Open polylines (mm, y down, top of the first line at y=0) of the text: one line per stroke.
    size_mm is the em height, as for the system fonts; spacing_mm is added between letters."""
    font = _load(family)
    k = size_mm / font.units
    polys = []
    baseline = font.ascent * k
    for line in (text or "").split("\n"):
        x = 0.0
        for ch in line:
            for p in glyph_lines(family, ch, size_mm, italic):
                polys.append([(x + px, baseline + py) for px, py in p])
            x += _glyph(font, ch)[0] * k + spacing_mm
        baseline += size_mm * LINE_SPACING
    return [p for p in polys if len(p) >= 2]
