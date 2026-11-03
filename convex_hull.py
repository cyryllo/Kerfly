"""
2D convex hull (Andrew's monotone chain algorithm).

Copyright (C) 2026 Kerfly contributors
This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.

Independent replacement for the snippet previously copied into K40 Whisperer;
the interface (hull2D().convex_hull / convexHullecoords) is kept unchanged.
"""


def _turn(a, b, c):
    """> 0 if a->b->c turns left (counter-clockwise), < 0 right, 0 collinear."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _half_hull(points):
    chain = []
    for p in points:
        while len(chain) > 1 and _turn(chain[-2], chain[-1], p) <= 0:
            chain.pop()
        chain.append(p)
    return chain


class hull2D:

    def convex_hull(self, points):
        """Return hull vertices counter-clockwise, starting at the lowest (x, y) point.

        Duplicate and collinear points are dropped.
        """
        pts = sorted(set(points))
        if len(pts) < 2:
            return pts
        lower = _half_hull(pts)
        upper = _half_hull(reversed(pts))
        # each chain ends where the other one starts
        return lower[:-1] + upper[:-1]

    def convexHullecoords(self, ecoords):
        """Hull of ecoords ([x, y, loop] rows) as a closed ecoords loop numbered 1."""
        hull = self.convex_hull([(row[0], row[1]) for row in ecoords])
        loop = [[x, y, 1] for (x, y) in hull]
        loop.append(loop[0])
        return loop
