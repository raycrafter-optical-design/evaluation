"""Tests for the pure helpers of the generic analysis."""

from evaluation_tools.analyze_zmx import interpolate_crossing, parse_zemax_surfaces

SYNTHETIC = """SURF 0
  TYPE STANDARD
  CURV 0.0 0 0 0 0 ""
  DISZ INFINITY
  DIAM 0 0 0 0 1 ""
SURF 1
  COMM first lens face
  TYPE STANDARD
  STOP
  CURV 0.02 0 0 0 0 ""
  DISZ 5.0
  GLAS N-BK7 0 0
  DIAM 12.7 1 0 0 1 ""
  CLAP 0 12.7 0
SURF 2
  TYPE COORDBRK
  PARM 3 45
  DISZ 0
  DIAM 0 0 0 0 1 ""
SURF 3
  TYPE STANDARD
  CURV 0.0 0 0 0 0 ""
  DISZ 0
  DIAM 3.25 0 0 0 1 ""
"""


def test_parse_skips_coordinate_breaks_and_reads_radius_and_flags():
    surfaces = parse_zemax_surfaces(SYNTHETIC)
    assert [s["zemax"] for s in surfaces] == [0, 1, 3]
    lens = surfaces[1]
    assert lens["radius_mm"] == 50.0
    assert lens["glass"] == "N-BK7"
    assert lens["is_stop"] and not lens["diam_is_automatic"]
    assert lens["clear_aperture_mm"] == 12.7
    assert surfaces[2]["diam_is_automatic"] and surfaces[2]["diam_mm"] == 3.25
    assert surfaces[0]["thickness_mm"] is None  # object at infinity


def test_crossing_interpolates_linearly():
    assert interpolate_crossing([0, 1, 2], [1.0, 0.8, 0.2], 0.5) == 1.5


def test_crossing_returns_last_x_if_never_reached():
    assert interpolate_crossing([0, 1, 2], [1.0, 0.9, 0.8], 0.5) == 2
