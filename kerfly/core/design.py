"""
A loaded design: the data the job generator works on.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from ecoords import ECoord


class Design:
    """Coordinates are in inches.

    raster          ECoord holding the raster image (and scan lines once computed)
    vector_engrave  ECoord, blue lines
    vector_cut      ECoord, red lines
    gcode           ECoord, paths read from a g-code file
    bounds          (xmin, xmax, ymin, ymax) of the design
    input_dpi       resolution of the raster image
    """

    def __init__(self):
        self.input_dpi = 1000.0
        self.reset()

    def reset(self):
        self.raster = ECoord()
        self.vector_engrave = ECoord()
        self.vector_cut = ECoord()
        self.gcode = ECoord()
        self.bounds = (0, 0, 0, 0)

    def get_bounds(self, rotate):
        """Design bounds, rotated 90 degrees if the job is rotated."""
        if rotate:
            ymin = self.bounds[0]
            ymax = self.bounds[1]
            xmin = -self.bounds[3]
            xmax = -self.bounds[2]
        else:
            xmin, xmax, ymin, ymax = self.bounds
        return (xmin, xmax, ymin, ymax)

    def origin_bounds(self, settings):
        """Bounds used as the job origin (zero when input coordinates are used for vectors)."""
        if settings.input_csys and self.raster.image is None:
            return 0.0, 0.0, 0.0, 0.0
        return self.get_bounds(settings.rotate)
