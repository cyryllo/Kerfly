"""
Design file loaders: SVG, DXF and G-code into a Design.

User interaction (questions about units or SVG scale) goes through callbacks,
so any GUI can provide its own dialogs.

Copyright (C) 2017-2026 Scorch (original code in K40 Whisperer)
Copyright (C) 2026 Kerfly contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See the LICENSE file for details.
"""
from dxf import DXF_CLASS
from g_code_library import G_Code_Rip
from svg_reader import SVG_READER, SVG_TEXT_EXCEPTION, SVG_PXPI_EXCEPTION

from .raster import _no_progress


class LoadCancelled(Exception):
    """The user cancelled a question asked during loading."""


# inches per DXF unit
DXF_UNIT_SCALE = {
    "Inches": 1.0,
    "Feet": 12.0,
    "Miles": 5280.0 * 12.0,
    "Millimeters": 1.0 / 25.4,
    "Centimeters": 1.0 / 2.54,
    "Meters": 1.0 / 254.0,          # sic: upstream value, kept for identical results
    "Kilometers": 1.0 / 254000.0,   # sic
    "Microinches": 1.0 / 1000000.0,
    "Mils": 1.0 / 1000.0,
}
DXF_UNITS = list(DXF_UNIT_SCALE)


def load_svg(filename, design, inkscape_path="", inkscape_timeout_s=180,
             reduced_memory=False, ask_pxpi=None, progress=_no_progress):
    """Load an SVG: red strokes -> vector cut, blue strokes -> vector engrave,
    everything else rendered by Inkscape into the raster image.

    ask_pxpi(svg_size, viewbox, inkscape_version) is called when the SVG does
    not define its physical size; it returns (pxpi, viewbox) or None to cancel.

    Returns a list of warning strings. Raises LoadCancelled or an exception
    describing the error.
    """
    design.reset()
    design.input_dpi = 500.0 if reduced_memory else 1000.0

    def new_reader():
        r = SVG_READER()
        r.image_dpi = design.input_dpi
        r.set_inkscape_path(inkscape_path)
        r.timout = int(inkscape_timeout_s)
        return r

    svg_reader = new_reader()
    pxpi = viewbox = None
    try:
        try:
            svg_reader.parse_svg(filename)
            svg_reader.make_paths()
        except SVG_PXPI_EXCEPTION:
            answer = None
            if ask_pxpi is not None:
                answer = ask_pxpi(svg_reader.SVG_Size, svg_reader.SVG_ViewBox,
                                  svg_reader.SVG_inkscape_version)
            if answer is None:
                raise LoadCancelled("SVG size not given")
            pxpi, viewbox = answer
            svg_reader = new_reader()
            svg_reader.parse_svg(filename)
            svg_reader.set_size(pxpi, viewbox)
            svg_reader.make_paths()
    except SVG_TEXT_EXCEPTION:
        svg_reader = new_reader()
        progress("Converting TEXT to PATHS.")
        svg_reader.parse_svg(filename)
        if pxpi is not None and viewbox is not None:
            svg_reader.set_size(pxpi, viewbox)
        svg_reader.make_paths(txt2paths=True)

    xmax = svg_reader.Xsize / 25.4
    ymax = svg_reader.Ysize / 25.4
    design.bounds = (0, xmax, 0, ymax)
    design.vector_cut.make_ecoords(svg_reader.cut_lines, scale=1 / 25.4)
    design.vector_engrave.make_ecoords(svg_reader.eng_lines, scale=1 / 25.4)
    design.raster.set_image(svg_reader.raster_PIL)

    warnings = []
    b = design.bounds
    veng = design.vector_engrave.bounds
    vcut = design.vector_cut.bounds
    margin = 0.0625  # avoid warnings for designs that are just at the page edge
    if b[0] > veng[0] + margin or b[0] > vcut[0] + margin or \
       b[1] < veng[1] - margin or b[1] < vcut[1] - margin or \
       b[2] > veng[2] + margin or b[2] > vcut[2] + margin or \
       b[3] < veng[3] - margin or b[3] < vcut[3] - margin:
        warnings.append(
            "Warning:\n"
            "There is vector cut or vector engrave data located outside of the SVG page bounds.\n\n"
            "K40 Whisperer will attempt to use all of the vector data.  "
            "Please verify that the vector data is not outside of your lasers working area before engraving.")
    return warnings


def _summarize_dxf_messages(text):
    """Collapse repeated DXF import messages into 'message (N places)' lines."""
    msg_split = text.split("\n")
    msg_split.sort()
    msg_split.append("")
    mcnt = 1
    msg_out = ""
    for i in range(1, len(msg_split)):
        if msg_split[i - 1] == msg_split[i]:
            mcnt = mcnt + 1
        else:
            if msg_split[i - 1] != "":
                msg_out = msg_out + "%s (%d places)\n" % (msg_split[i - 1], mcnt)
            mcnt = 1
    return msg_out


def load_dxf(filename, design, ask_units=None):
    """Load a DXF: blue entities or layers named '*engrave*' -> vector engrave,
    everything else -> vector cut.

    ask_units() is called when the file does not declare its units; it returns
    one of DXF_UNITS or None to cancel.

    Returns a list of warning strings. Raises LoadCancelled or an exception
    describing the error.
    """
    design.reset()
    dxf_import = DXF_CLASS()
    tolerance = .0005
    with open(filename) as fd:
        dxf_import.GET_DXF_DATA(fd, lin_tol=tolerance, get_units=True, units=None)
        fd.seek(0)
        dxf_units = dxf_import.units
        if dxf_units == "Unitless":
            dxf_units = ask_units() if ask_units is not None else None
        if dxf_units not in DXF_UNIT_SCALE:
            raise LoadCancelled("DXF units not given")
        dxf_scale = DXF_UNIT_SCALE[dxf_units]
        dxf_import.GET_DXF_DATA(fd, lin_tol=tolerance / dxf_scale, get_units=False, units=None)

    engrave = dxf_import.DXF_COORDS_GET_TYPE(engrave=True, new_origin=False)
    cut = dxf_import.DXF_COORDS_GET_TYPE(engrave=False, new_origin=False)

    warnings = []
    if dxf_import.dxf_messages != "":
        warnings.append(_summarize_dxf_messages(dxf_import.dxf_messages))

    design.vector_cut.make_ecoords(cut, scale=dxf_scale)
    design.vector_engrave.make_ecoords(engrave, scale=dxf_scale)
    vc = design.vector_cut.bounds
    ve = design.vector_engrave.bounds
    design.bounds = (min(vc[0], ve[0]), max(vc[1], ve[1]),
                     min(vc[2], ve[2]), max(vc[3], ve[3]))
    return warnings


def load_gcode(filename, design):
    """Load a g-code file as laser paths. Returns a list of reader warnings."""
    design.reset()
    g_rip = G_Code_Rip()
    messages = g_rip.Read_G_Code(filename, XYarc2line=True, arc_angle=2, units="in", Accuracy="")
    ecoords = g_rip.generate_laser_paths(g_rip.g_code_data)
    design.gcode.set_ecoords(ecoords, data_sorted=True)
    design.bounds = design.gcode.bounds
    return list(messages) if messages else []
