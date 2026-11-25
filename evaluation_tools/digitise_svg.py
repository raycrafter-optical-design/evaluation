"""Read data points out of the vector SVG plots that ship with the TWINKLE Zemax files.

The plots were drawn by Zemax (relative illumination) and by MATLAB (scan-angle curves). Both
are vector files, so marker and vertex coordinates are exact apart from the rounding of the
axis calibration. The values are still *read off a plot*, so the pages label them as digitised.
"""

from __future__ import annotations

import re
from pathlib import Path


def relative_illumination_curve(svg_path: Path) -> dict[str, list[float]]:
    """Field angle (deg) and relative illumination from the Zemax relative-illumination SVG.

    The blue curve is a polyline whose points are in SVG pixels. The axis is calibrated from the
    tick labels: x labels ``0`` ... ``12.0`` degrees and y labels ``0`` ... ``1.0``.
    """
    text = svg_path.read_text(encoding="utf-8")
    points = _entity_points(text, _curve_entity(text))
    x_ticks = _tick_positions(text, axis="x")
    y_ticks = _tick_positions(text, axis="y")
    (x_pixel_0, x_value_0), (x_pixel_1, x_value_1) = x_ticks[0], x_ticks[-1]
    (y_pixel_0, y_value_0), (y_pixel_1, y_value_1) = y_ticks[0], y_ticks[-1]
    field_deg = [
        x_value_0 + (px - x_pixel_0) * (x_value_1 - x_value_0) / (x_pixel_1 - x_pixel_0)
        for px, _ in points
    ]
    illumination = [
        y_value_0 + (py - y_pixel_0) * (y_value_1 - y_value_0) / (y_pixel_1 - y_pixel_0)
        for _, py in points
    ]
    return {"field_deg": field_deg, "relative_illumination": illumination}


def _curve_entity(text: str) -> str:
    """Name of the XML entity holding the points of the blue (data) polyline."""
    for match in re.finditer(r'<polyline style="&(\w+);" points="&(\w+);"', text):
        style = re.search(rf"<!ENTITY {match.group(1)} '([^']*)'", text).group(1)
        if "rgb(0,0,255)" in style:
            return match.group(2)
    raise ValueError("no blue polyline found")


def _entity_points(text: str, entity: str) -> list[tuple[float, float]]:
    numbers = re.search(rf"<!ENTITY {entity} '([^']*)'", text).group(1).split()
    values = [float(n) for n in numbers]
    return list(zip(values[0::2], values[1::2]))


def _tick_positions(text: str, axis: str) -> list[tuple[float, float]]:
    """``(pixel, value)`` for the numeric tick labels of one axis, in label order."""
    ticks = []
    for match in re.finditer(
        r'<text[^>]*transform="matrix\(1 0 0 1 ([\d.]+) ([\d.]+) \) "[^>]*>'
        r"([\d.]+)</text>",
        text,
    ):
        pixel_x, pixel_y, label = float(match[1]), float(match[2]), float(match[3])
        is_x_label = pixel_y > 700  # the x labels sit under the plot, the y labels beside it
        if is_x_label and axis == "x":
            ticks.append((pixel_x, label))
        elif not is_x_label and axis == "y" and pixel_x < 200:
            # y labels are placed at the text anchor; the tick is at their vertical centre
            ticks.append((pixel_y, label))
    return sorted(ticks)[::-1] if axis == "y" else sorted(ticks)


def scan_curves(svg_path: Path) -> dict[str, list[float]]:
    """Field curvature, radial FWHM and axial FWHM against galvo angle from the MATLAB SVG.

    Three stacked panels, each with blue circle markers. The x axis is -11 to 11 degrees (ticks
    every 2 degrees, -10 at one pixel position and 10 at another), and the y limits are the
    ones set in ``plot_zmax.m``: curvature -1.1 to 1.1, radial 0 to 2.5, axial 0 to 10 (um).
    """
    text = svg_path.read_text(encoding="utf-8")
    markers = [
        (float(m[1]), float(m[2]))
        for m in re.finditer(
            r'<g transform="translate\(([-\d.]+),([-\d.]+)\)"[^>]*>\s*<circle r="3"', text
        )
    ]
    ticks = sorted(
        {
            float(m[1])
            for m in re.finditer(
                r'<line y2="[\d.]+" style="fill:none;" x1="([\d.]+)" x2="\1"', text
            )
        }
    )
    ticks = [t for t in ticks if 73 < t < 507]  # drop the frame edges, which are -11 and 11
    x_minus_10, x_plus_10 = ticks[0], ticks[-1]
    frames = sorted(
        {
            float(m[1])
            for m in re.finditer(
                r'<line y2="([\d.]+)" style="fill:none;" x1="73" x2="507" y1="\1"', text
            )
        }
    )
    # frames come in (top, bottom) pairs, one pair per panel
    panels = [(frames[i], frames[i + 1]) for i in range(0, len(frames), 2)]
    limits = [(-1.1, 1.1), (0.0, 2.5), (0.0, 10.0)]
    names = ["axial_peak_offset_um", "radial_fwhm_um", "axial_fwhm_um"]
    out: dict[str, list[float]] = {"angle_deg": [], **{name: [] for name in names}}
    first_panel = [m for m in markers if panels[0][0] <= m[1] <= panels[0][1]]
    angles = sorted(
        {round(-10 + 20 * (px - x_minus_10) / (x_plus_10 - x_minus_10), 3) for px, _ in first_panel}
    )
    out["angle_deg"] = angles
    for name, (top, bottom), (low, high) in zip(names, panels, limits):
        in_panel = {
            round(-10 + 20 * (px - x_minus_10) / (x_plus_10 - x_minus_10), 3): low
            + (bottom - py) * (high - low) / (bottom - top)
            for px, py in markers
            if top <= py <= bottom
        }
        out[name] = [in_panel[a] for a in angles]
    return out
