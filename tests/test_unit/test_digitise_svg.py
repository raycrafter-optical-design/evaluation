"""Tests for reading data out of vector plots, using minimal synthetic SVGs."""

from evaluation_tools.digitise_svg import relative_illumination_curve

SVG = """<?xml version="1.0"?>
<!DOCTYPE svg [
  <!ENTITY STYLE 'stroke:rgb(0,0,255);fill:none;'>
  <!ENTITY POINTS '100 600 200 400 300 100 '>
]>
<svg xmlns="http://www.w3.org/2000/svg">
<polyline style="&STYLE;" points="&POINTS;" id="L1" />
<text transform="matrix(1 0 0 1 100 720 ) " x="0" y="0">0</text>
<text transform="matrix(1 0 0 1 300 720 ) " x="0" y="0">12.0</text>
<text transform="matrix(1 0 0 1 90 600 ) " x="0" y="0">0</text>
<text transform="matrix(1 0 0 1 90 100 ) " x="0" y="0">1.0</text>
</svg>
"""


def test_relative_illumination_is_calibrated_from_tick_labels(tmp_path):
    path = tmp_path / "ri.svg"
    path.write_text(SVG, encoding="utf-8")
    curve = relative_illumination_curve(path)
    assert curve["field_deg"] == [0.0, 6.0, 12.0]
    assert [round(v, 3) for v in curve["relative_illumination"]] == [0.0, 0.4, 1.0]
