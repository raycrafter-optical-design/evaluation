"""Build the page of a design analysed with ``analyze_zmx.py``.

``designs/<name>/HTML_summary/template.html`` holds the design's own sections (hand-written
prose with placeholders). This module wraps it in the shared page frame (``page_wrapper.html``:
head, contents rail, header, footer, 3D viewer script) and fills the placeholders from
``optiland_analysis/results.json``, ``comparison.json`` and ``design.json``.

Placeholders in the template: ``@@TALLY@@``, ``@@VERDICT_ROWS@@``, ``@@EXCLUDED@@``,
``@@LENS_ROWS@@``, ``@@SD_ROWS@@`` and ``$GENERATED``.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from evaluation_tools import build_summary

FRAME_PATH = Path(__file__).with_name("page_wrapper.html")


def excluded_html(results: dict) -> str:
    """Callout listing the semi-diameter rows that were not scored, with the reason."""
    excluded = [c for c in results["semi_diameter_check"] if c.get("excluded_reason")]
    if not excluded:
        return ""
    items = "".join(
        f"<p><strong>Surface {c['zemax_surface']}</strong>: Zemax {c['zemax_mm']:.4f} mm, "
        f"Optiland {c['optiland_mm']:.4f} mm. {html.escape(c['excluded_reason'])}</p>"
        for c in excluded
    )
    return f'<div class="callout warn"><strong class="h">Not scored</strong>{items}</div>'


def semi_diameter_rows_html(results: dict) -> str:
    """Rows for the full semi-diameter table (including unscored rows)."""
    lines = []
    for check in results["semi_diameter_check"]:
        ratio = check["optiland_mm"] / check["zemax_mm"]
        note = "not scored" if check.get("excluded_reason") else ""
        lines.append(
            f'      <tr><td class="num">{check["zemax_surface"]}</td>'
            f"<td>{html.escape(check['comment'])}</td>"
            f'<td class="num">{check["zemax_mm"]:.4f}</td>'
            f'<td class="num">{check["optiland_mm"]:.4f}</td>'
            f'<td class="num">{ratio:.4f}</td><td>{note}</td></tr>'
        )
    return "\n".join(lines)


def lens_rows_html(results: dict) -> str:
    """Prescription rows: Zemax radius, Optiland radius, thickness, glass, semi-diameter."""
    lines = []
    for row in results["lens_table"]:
        radius = build_summary.format_value(row["radius_mm"])
        optiland_radius = build_summary.format_value(row["optiland_radius_mm"])
        thickness = (
            "∞"
            if row["thickness_mm"] is None
            else build_summary.format_value(row["thickness_mm"], 4)
        )
        glass = "MIRROR" if row["is_mirror"] else (row["glass"] or "")
        semi = build_summary.format_value(row["diam_mm"], 3) + (
            "" if row["diam_is_automatic"] else " (fixed)"
        )
        aperture = (
            ""
            if row["clear_aperture_mm"] is None
            else build_summary.format_value(row["clear_aperture_mm"], 3)
        )
        kind = row["type"] + (" (stop)" if row["is_stop"] else "")
        lines.append(
            f'      <tr><td class="num">{row["zemax"]}</td><td>{html.escape(row["comment"])}</td>'
            f"<td>{html.escape(kind)}</td>"
            f'<td class="num">{radius}</td><td class="num">{optiland_radius}</td>'
            f'<td class="num">{thickness}</td><td class="mono">{html.escape(glass)}</td>'
            f'<td class="num">{semi}</td><td class="num">{aperture}</td></tr>'
        )
    return "\n".join(lines)


def navigation_html(body: str) -> str:
    """Contents rail built from the ``<section id=...><h2>`` pairs in the page body."""
    items = []
    for match in re.finditer(
        r'<section id="([\w-]+)"[^>]*>\s*(?:<div[^>]*>)?\s*<h2>(.*?)</h2>', body
    ):
        items.append(f'    <li><a href="#{match[1]}">{match[2]}</a></li>')
    return "\n".join(items)


def meta_html(design: dict, results: dict) -> str:
    """The row of small facts under the title."""
    wavelengths = ", ".join(f"{w:g}" for w in results["wavelengths_um"])
    fields = ", ".join(f"{f:g}" for f in results["fields_deg"])
    parts = [
        f"optiland <b>{html.escape(design['optiland_version'])}</b>",
        f"λ <b>{wavelengths} µm</b>",
        f"Zemax <b>{html.escape(design['zemax_version'])}</b>",
        f"EPD <b>{results['EPD_mm']:g} mm</b>",
        f"fields <b>{fields}°</b>",
        "run <b>$GENERATED</b>",
    ]
    return "\n".join(f"    <span>{part}</span>" for part in parts)


def build_design(design_dir: Path) -> dict:
    """Write ``HTML_summary/index.html`` for one generic design; return its landing entry."""
    design = json.loads((design_dir / "design.json").read_text(encoding="utf-8"))
    results = json.loads((design_dir / "optiland_analysis" / "results.json").read_text("utf-8"))
    comparison = json.loads((design_dir / "comparison.json").read_text(encoding="utf-8"))
    documents = {"results.json": results}
    rows = build_summary.evaluate_rows(comparison, documents)
    counts = build_summary.tally_counts(rows)

    body = (design_dir / "HTML_summary" / "template.html").read_text(encoding="utf-8")
    body = (
        body.replace("@@TALLY@@", build_summary.tally_html(counts))
        .replace("@@VERDICT_ROWS@@", build_summary.verdict_rows_html(rows))
        .replace("@@EXCLUDED@@", excluded_html(results))
        .replace("@@LENS_ROWS@@", lens_rows_html(results))
        .replace("@@SD_ROWS@@", semi_diameter_rows_html(results))
    )
    frame = FRAME_PATH.read_text(encoding="utf-8")
    page = (
        frame.replace("@@TITLE@@", html.escape(design["title"]))
        .replace("@@LEDE@@", design["lede"])
        .replace("@@META@@", meta_html(design, results))
        .replace("@@NAV@@", navigation_html(body))
        .replace("@@BODY@@", body)
    )
    if 'id="viewer"' not in body:  # drop the 3D viewer script when the page has no viewer
        page = re.sub(r"<!--VIEWER-->.*?<!--/VIEWER-->", "", page, flags=re.S)
    page = page.replace("$GENERATED", date.today().isoformat())
    (design_dir / "HTML_summary" / "index.html").write_text(page, encoding="utf-8")
    return {"design": design, "counts": counts, "dir_name": design_dir.name}
