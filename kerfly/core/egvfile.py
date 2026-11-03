"""
Reading EGV (LHYMICRO-GL) files.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from dataclasses import dataclass
from typing import List


@dataclass
class EgvFile:
    data: List[int]
    x_start_mils: int = 0
    y_start_mils: int = 0
    x_end_mils: int = 0
    y_end_mils: int = 0

    @property
    def has_end_position(self):
        """Files that end away from where they started can only run one pass."""
        return self.x_end_mils != 0 or self.y_end_mils != 0

    def return_move(self):
        """(dx, dy) mils to bring the head back to the start after the job."""
        if not self.has_end_position:
            return 0, 0
        return -(self.x_end_mils - self.x_start_mils), self.y_end_mils - self.y_start_mils


def parse_egv(text):
    """Parse EGV file contents: a header, then '%y0%x0%y1%x1%' start/end
    positions in mils, then the command stream (whitespace is ignored)."""
    pos = text.find("%")
    if pos < 0:
        raise ValueError("Not an EGV file (no '%' position block).")
    values = []
    for _ in range(4):
        end = text.find("%", pos + 1)
        if end < 0:
            raise ValueError("Not an EGV file (incomplete position block).")
        values.append(int(text[pos + 1:end]))
        pos = end
    y_start, x_start, y_end, x_end = values
    data = [ord(c) for c in text[pos + 1:] if c not in "\r\n "]
    if not data:
        raise ValueError("The EGV file contains no laser data.")
    return EgvFile(data, x_start, y_start, x_end, y_end)


def read_egv_file(filename):
    with open(filename, "r", encoding="latin-1") as f:
        return parse_egv(f.read())
