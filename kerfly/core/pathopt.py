"""
Path ordering for vector jobs: nearest-neighbour loop ordering and
"inside first" ordering (inner loops are cut before the loops containing them,
so parts do not drop out before their holes are cut).

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from math import sqrt


def sort_paths(ecoords, i_loop=2):
    """Order loops greedily by distance from the end of the previous loop.

    Returns a list of [first_index, last_index] pairs into ecoords; a pair with
    first > last means the loop is traversed backwards.
    """
    # find loop ends
    Lbeg = []
    Lend = []
    if len(ecoords) > 0:
        Lbeg.append(0)
        loop_old = ecoords[0][i_loop]
        for i in range(1, len(ecoords)):
            loop = ecoords[i][i_loop]
            if loop != loop_old:
                Lbeg.append(i)
                Lend.append(i - 1)
            loop_old = loop
        Lend.append(i)

    # find new order based on distance to next beg or end
    order_out = []
    use_beg = 0
    if len(ecoords) > 0:
        order_out.append([Lbeg[0], Lend[0]])
    inext = 0
    total = len(Lbeg)
    for i in range(total - 1):
        if use_beg == 1:
            ii = Lbeg.pop(inext)
            Lend.pop(inext)
        else:
            ii = Lend.pop(inext)
            Lbeg.pop(inext)

        Xcur = ecoords[ii][0]
        Ycur = ecoords[ii][1]

        dx = Xcur - ecoords[Lbeg[0]][0]
        dy = Ycur - ecoords[Lbeg[0]][1]
        min_dist = dx * dx + dy * dy

        dxe = Xcur - ecoords[Lend[0]][0]
        dye = Ycur - ecoords[Lend[0]][1]
        min_diste = dxe * dxe + dye * dye

        inext = 0
        inexte = 0
        for j in range(1, len(Lbeg)):
            dx = Xcur - ecoords[Lbeg[j]][0]
            dy = Ycur - ecoords[Lbeg[j]][1]
            dist = dx * dx + dy * dy
            if dist < min_dist:
                min_dist = dist
                inext = j
            dxe = Xcur - ecoords[Lend[j]][0]
            dye = Ycur - ecoords[Lend[j]][1]
            diste = dxe * dxe + dye * dye
            if diste < min_diste:
                min_diste = diste
                inexte = j
        if min_diste < min_dist:
            inext = inexte
            order_out.append([Lend[inexte], Lbeg[inexte]])
            use_beg = 1
        else:
            order_out.append([Lbeg[inext], Lend[inext]])
            use_beg = 0
    return order_out


def point_inside_polygon(x, y, poly):
    """Ray casting test. Returns 1 if (x, y) is inside poly, -1 otherwise.
    poly is a list of (x, y) pairs."""
    n = len(poly)
    inside = -1
    p1x = poly[0][0]
    p1y = poly[0][1]
    for i in range(n + 1):
        p2x = poly[i % n][0]
        p2y = poly[i % n][1]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = inside * -1
        p1x, p1y = p2x, p2y
    return inside


class _InsideFirstOrder:
    """Orders loops so that loops lying inside another loop come first."""

    def __init__(self, cuts):
        n = len(cuts)
        self.tree = []          # tree[i]: loops found inside loop i
        for iloop in range(n):
            self.tree.append([])
            ipoly = cuts[iloop]
            if ipoly != []:
                for jloop in range(n):
                    if jloop != iloop:
                        inside = 0
                        inside = inside + point_inside_polygon(cuts[jloop][0][0], cuts[jloop][0][1], ipoly)
                        if inside > 0:
                            self.tree[iloop].append(jloop)
        for i in range(n):
            self._remove_self_references([i], self.tree[i])

        self.order = []
        self.loops = list(range(n))
        for i in range(n):
            if self.tree[i] != []:
                self._add_list(self.tree[i])
                self.tree[i] = []
            if self.loops[i] != []:
                self.order.append(self.loops[i])
                self.loops[i] = []

    def _remove_self_references(self, loop_numbers, loops):
        for i in range(0, len(loops)):
            for j in range(0, len(loop_numbers)):
                if loops[i] == loop_numbers[j]:
                    loops.pop(i)
                    return
            if self.tree[loops[i]] != []:
                loop_numbers.append(loops[i])
                self._remove_self_references(loop_numbers, self.tree[loops[i]])

    def _add_list(self, items):
        for i in items:
            # Upstream note: this try/except works around a recursion error and
            # should be fixed properly; kept as-is to preserve behaviour.
            try:
                if self.tree[i] != []:
                    self._add_list(self.tree[i])
                    self.tree[i] = []
            except Exception:
                pass
            if self.loops[i] != []:
                self.order.append(self.loops[i])
                self.loops[i] = []


def optimize_paths(ecoords, inside_check=True):
    """Reorder ecoords ([x, y, loop] rows) for cutting.

    Loops are first ordered by distance (sort_paths); consecutive loops whose
    ends touch (within 0.004 in) are merged. With inside_check, loops inside
    other loops are moved before them. Loop numbers are renumbered.
    """
    order_out = sort_paths(ecoords)
    lastx = -999
    lasty = -999
    Acc = 0.004
    cuts = []

    for line in order_out:
        temp = line
        if temp[0] > temp[1]:
            step = -1
        else:
            step = 1

        loop_old = -1

        for i in range(temp[0], temp[1] + step, step):
            x1 = ecoords[i][0]
            y1 = ecoords[i][1]
            loop = ecoords[i][2]
            # check and see if we need to move to a new discontinuous start point
            if loop != loop_old:
                dx = x1 - lastx
                dy = y1 - lasty
                dist = sqrt(dx * dx + dy * dy)
                if dist > Acc:
                    cuts.append([[x1, y1]])
                else:
                    cuts[-1].append([x1, y1])
            else:
                cuts[-1].append([x1, y1])
            lastx = x1
            lasty = y1
            loop_old = loop

    if inside_check:
        order = _InsideFirstOrder(cuts).order
    else:
        order = range(len(cuts))

    ecoords_out = []
    for i in order:
        for coord in cuts[i]:
            ecoords_out.append([coord[0], coord[1], i])
    return ecoords_out
