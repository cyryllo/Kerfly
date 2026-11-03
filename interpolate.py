"""
Piecewise linear interpolation over a table of (x, y) points.

Copyright (C) 2026 Kerfly contributors
This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.

Independent replacement for the snippet previously copied into K40 Whisperer;
the interface (interpolate(xs, ys)[x]) is kept unchanged.
"""
from bisect import bisect_left


class interpolate(object):
    """Table lookup with linear interpolation; values outside the table are clamped.

    xs must be strictly increasing. For x inside the table the segment whose
    left end is the largest knot strictly below x is used, so x equal to an
    interior knot is evaluated on the segment ending at that knot.
    """

    def __init__(self, x_list, y_list):
        xs = [float(v) for v in x_list]
        ys = [float(v) for v in y_list]
        for k in range(1, len(xs)):
            if xs[k] <= xs[k - 1]:
                raise ValueError("x_list must be in strictly ascending order!")
        self.x_list = xs
        self.y_list = ys
        self.slopes = []
        for k in range(len(xs) - 1):
            self.slopes.append((ys[k + 1] - ys[k]) / (xs[k + 1] - xs[k]))

    def __getitem__(self, x):
        xs = self.x_list
        if x <= xs[0]:
            return self.y_list[0]
        if x >= xs[-1]:
            return self.y_list[-1]
        seg = bisect_left(xs, x) - 1
        return self.y_list[seg] + self.slopes[seg] * (x - xs[seg])
