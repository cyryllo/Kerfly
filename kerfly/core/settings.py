"""
Job settings: every user setting that influences the data sent to the laser.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from dataclasses import dataclass


@dataclass
class JobSettings:
    """Values are stored already converted to numbers, exactly the way the
    original K40 Whisperer code converted its Tk variables at the point of use,
    so job output stays byte-identical."""

    # machine
    board_name: str = "LASER-M2"
    units: str = "mm"                 # "mm" (speeds in mm/s) or "in" (speeds in in/min)
    home_upper_right: bool = False    # HomeUR
    input_csys: bool = False          # inputCSYS: use design coordinates instead of design corner
    power_per_stage: bool = False     # M3 board with power control shown: power set via USB per stage
    max_power: float = 30.0

    # transforms
    mirror: bool = False
    rotate: bool = False
    x_scale: float = 1.0              # LaserXscale
    y_scale: float = 1.0              # LaserYscale
    rotary: bool = False
    rotary_scale: float = 1.0         # LaserRscale
    rapid_feed: float = 0.0           # used only with rotary

    # ordering
    inside_first: bool = True

    # raster engrave
    raster_feed: float = 100.0        # Reng_feed
    raster_passes: int = 1
    raster_power: float = 0.5         # fraction of max_power (M3 only)
    raster_step: float = 0.002        # inches between scan lines
    engrave_up: bool = False
    negate: bool = False
    halftone: bool = True
    halftone_dpi: float = 500.0       # ht_size
    bezier_m1: float = 2.5
    bezier_m2: float = 0.5
    bezier_weight: float = 3.5

    # vector engrave
    vengrave_feed: float = 20.0
    vengrave_passes: int = 1
    vengrave_power: float = 0.5

    # vector cut
    vcut_feed: float = 10.0
    vcut_passes: int = 1
    vcut_power: float = 0.5

    # g-code
    gcode_passes: int = 1
    gcode_power: float = 0.5

    # boundary trace
    trace_feed: float = 50.0          # trace_speed
    trace_with_laser: int = 0         # trace_w_laser
    trace_gap: float = 0.0            # in the units given by `units`
    trace_power: float = 0.5

    @property
    def feed_factor(self):
        """Multiplier converting the stored feeds to mm/s."""
        return 25.4 / 60.0 if self.units == "in" else 1.0

    @property
    def units_scale(self):
        """Number of setting units per inch."""
        return 1.0 if self.units == "in" else 25.4

    @property
    def raster_step_mils(self):
        """Scan line step in 1/1000 inch, rounded like the original."""
        return int(round(self.raster_step * 1000.0, 1))

    @property
    def xy_scale(self):
        """(x, y) calibration scale including the rotary factor."""
        y = self.y_scale * self.rotary_scale if self.rotary else self.y_scale
        return self.x_scale, y
