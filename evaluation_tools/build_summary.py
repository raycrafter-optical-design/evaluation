"""Generate the HTML summaries: one page per design, plus the landing page.

Usage (from the repository root)::

    uv run python -m evaluation_tools.build_summary

For each ``designs/<name>/`` this reads ``comparison.json``, ``optiland_analysis/results.json``
and ``Zemax_reference_output/zemax_digitised.json`` and fills
``HTML_summary/template.html`` to give ``HTML_summary/index.html``. It then writes ``index.html``
in the repository root, listing the designs. The output is committed, so GitHub Pages needs no
build step.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_PATH = Path(__file__).with_name("upstream_issues.json")
STATUS_LABEL = {"match": "Match", "partial": "Partial", "fail": "Fail"}
STATUS_CLASS = {"match": "ok", "partial": "warn", "fail": "bad"}
WAVELENGTH_KEYS = ["0.85", "0.94", "1.1"]


# ------------------------------------------------------------------ upstream links ---
def upstream_links_html(issue_number: str) -> str:
    """ "Upstream: ..." line for local issue ``issue_number`` (links, or 'not yet filed')."""
    links = json.loads(UPSTREAM_PATH.read_text(encoding="utf-8"))["links"].get(issue_number, [])
    if not links:
        return '<span class="src">Upstream: not yet filed.</span>'
    parts = [
        f'<a href="{url}">{html.escape(label)}</a>' + (f" ({html.escape(note)})" if note else "")
        for label, url, note in links
    ]
    return f'<span class="src">Upstream: {", ".join(parts)}.</span>'


def link_upstream_issues(page: str) -> str:
    """Add an upstream line to every ``<li><b>N. ...`` entry of the page's issue list."""
    return re.sub(
        r"(<li><b>(\d+)\. .*?)(</li>)",
        lambda m: m.group(1) + " " + upstream_links_html(m.group(2)) + m.group(3),
        page,
        flags=re.S,
    )


# ------------------------------------------------------------------ comparison ---
def resolve(reference: str, documents: dict[str, dict]) -> float:
    """Look up ``"file.json:key/key/index"`` in the loaded JSON ``documents``.

    Keys are separated by ``/`` (wavelength keys such as ``1.1`` contain a dot). A key that
    parses as an integer indexes a list; negative values count from the end.
    """
    file_name, _, key_path = reference.partition(":")
    node = documents[file_name]
    for key in key_path.split("/"):
        node = node[int(key)] if isinstance(node, list) else node[key]
    return float(node)


def classify(zemax: list[float], optiland: list[float], row: dict) -> tuple[str, float]:
    """Return ``(status, worst_difference)`` for one comparison row.

    ``abs`` rows compare absolute differences against ``tol`` and ``partial_tol``. ``ratio``
    rows compare optiland/zemax, so ``tol`` is a relative tolerance around 1 and ``partial_tol``
    is the largest acceptable ratio (and its inverse).
    """
    if row["mode"] == "abs":
        worst = max(abs(o - z) for z, o in zip(zemax, optiland))
        if worst <= row["tol"]:
            return "match", worst
        return ("partial" if worst <= row["partial_tol"] else "fail"), worst
    ratios = [o / z for z, o in zip(zemax, optiland)]
    worst = max(max(r, 1 / r) for r in ratios)
    if worst <= 1 + row["tol"]:
        return "match", worst
    return ("partial" if worst <= row["partial_tol"] else "fail"), worst


def format_number(value: float, decimals: int) -> str:
    """Format with a true minus sign, as the tables use."""
    return f"{value:.{decimals}f}".replace("-", "−")


def evaluate_rows(comparison: dict, documents: dict[str, dict]) -> list[dict]:
    """Add values and a computed ``result`` to every row of ``comparison.json``."""
    evaluated = []
    for row in comparison["rows"]:
        row = dict(row)
        if "status" in row:  # judged by eye, no numbers
            row["result"] = row["status"]
            row["zemax_text"] = row["optiland_text"] = "see below"
            row["difference_text"] = "—"
        else:
            if "zemax_path" in row:
                zemax = [resolve(p, documents) for p in row["zemax_path"]]
            else:
                zemax = row["zemax"]
            optiland = [resolve(p, documents) for p in row["optiland"]]
            row["result"], worst = classify(zemax, optiland, row)
            decimals = row["decimals"]
            row["zemax_text"] = " / ".join(format_number(v, decimals) for v in zemax)
            row["optiland_text"] = " / ".join(format_number(v, decimals) for v in optiland)
            if row["mode"] == "abs":
                row["difference_text"] = "<0.0001" if worst < 0.0001 else f"{worst:.4f}".rstrip("0")
            else:
                if worst < 1.1:
                    row["difference_text"] = f"{(worst - 1) * 100:.2f}%"
                else:
                    row["difference_text"] = (
                        f"{worst:.0f}×" if worst >= 10 else f"about {worst:.0f}×"
                    )
        evaluated.append(row)
    return evaluated


def verdict_rows_html(rows: list[dict]) -> str:
    """The table body of the verdict table."""
    lines = []
    for row in rows:
        source = row.get("zemax_source", "")
        label = html.escape(row["label"])
        if source:
            label += f'<span class="src">Zemax: {html.escape(source)}</span>'
        status = row["result"]
        lines.append(
            f'    <tr><td>{label}</td><td class="num">{row["zemax_text"]}</td>'
            f'<td class="num">{row["optiland_text"]}</td><td class="num">{row["difference_text"]}</td>'
            f'<td><span class="chip {STATUS_CLASS[status]}">{STATUS_LABEL[status]}</span></td></tr>'
        )
    return "\n".join(lines)


def tally_counts(rows: list[dict]) -> dict[str, int]:
    """Number of rows with each status."""
    counts = {"match": 0, "partial": 0, "fail": 0}
    for row in rows:
        counts[row["result"]] += 1
    return counts


def tally_html(counts: dict[str, int]) -> str:
    """The three tally boxes."""
    labels = {"match": "matching", "partial": "partial", "fail": "failing"}
    colours = {"match": "ok", "partial": "warn", "fail": "bad"}
    return "".join(
        f'<div><b style="color:var(--{colours[k]})">{counts[k]}</b><span>{labels[k]}</span></div>'
        for k in ("match", "partial", "fail")
    )


# ------------------------------------------------------------------ page parts ---
def format_value(value: float | None, decimals: int = 3) -> str:
    """Number for the lens table: ``∞`` for None, trailing zeros trimmed."""
    if value is None:
        return "∞"
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def lens_rows_html(rows: list[dict]) -> str:
    """Table body for the lens data section."""
    out = []
    for r in rows:
        if r["zemax"] == 0:
            thickness = "∞"
        elif r.get("thickness") is None:
            thickness = "—"
        else:
            thickness = format_value(r["thickness"], 4)
        indices = r["n"] or [None, None, None]
        is_glass = r["material"] not in ("Air", "MIRROR")
        index_text = [f"{x:.5f}" if (x is not None and is_glass) else "" for x in indices]
        kind = r["type"] + (" (stop)" if r["stop"] else "")
        out.append(
            "      <tr>"
            f'<td class="num">{r["zemax"]}</td>'
            f"<td>{html.escape(r['comment'])}</td>"
            f"<td>{html.escape(kind)}</td>"
            f'<td class="num">{format_value(r["radius"])}</td>'
            f'<td class="num">{thickness}</td>'
            f'<td class="mono">{html.escape(r["material"])}</td>'
            + "".join(f'<td class="num">{x}</td>' for x in index_text)
            + "</tr>"
        )
    return "\n".join(out)


def chart_data(results: dict, zemax_digitised: dict) -> dict:
    """Data for the two SVG charts: Zemax curves (digitised) and Optiland points."""
    return {
        "zdeg": zemax_digitised["field_deg"],
        "z_wfe": zemax_digitised["rms_wfe_waves"],
        "z_strehl": zemax_digitised["strehl"],
        "o_wdeg": results["rms"]["deg_wfe"],
        "o_wfe": results["rms"]["wfe_waves"],
        "o_sdeg": results["strehl"]["deg"],
        "o_strehl": results["strehl"]["fft"],
    }


def load_json(path: Path) -> dict:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------- design ---
def build_design(design_dir: Path) -> dict:
    """Write ``HTML_summary/index.html`` for one design and return its landing-page entry."""
    design = load_json(design_dir / "design.json")
    if design.get("analysis") == "generic":  # designs analysed by analyze_zmx.py
        from evaluation_tools import build_generic

        return build_generic.build_design(design_dir)
    results = load_json(design_dir / "optiland_analysis" / "results.json")
    digitised = load_json(design_dir / "Zemax_reference_output" / "zemax_digitised.json")
    comparison = load_json(design_dir / "comparison.json")
    documents = {"results.json": results, "zemax_digitised.json": digitised}
    rows = evaluate_rows(comparison, documents)
    counts = tally_counts(rows)

    template = (design_dir / "HTML_summary" / "template.html").read_text(encoding="utf-8")
    page = (
        template.replace("@@TITLE@@", html.escape(design["name"]))
        .replace("@@TALLY@@", tally_html(counts))
        .replace("@@VERDICT_ROWS@@", verdict_rows_html(rows))
        .replace("$LENS_ROWS", lens_rows_html(results["lens_table"]))
        .replace("$GENERATED", date.today().isoformat())
        .replace("@@CHART_DATA@@", json.dumps(chart_data(results, digitised)))
    )
    page = link_upstream_issues(page)
    (design_dir / "HTML_summary" / "index.html").write_text(page, encoding="utf-8")
    return {"design": design, "counts": counts, "dir_name": design_dir.name}


# --------------------------------------------------------------------- landing ---
LANDING_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Optiland and RayCrafter against Zemax</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap" style="grid-template-columns:minmax(0,1fr)">
<main>
<header class="top">
  <p class="eyebrow">RayCrafter evaluation</p>
  <h1>Optiland and RayCrafter against Zemax</h1>
  <p class="lede">For each optical design, how closely does the open-source ray tracer
  <a href="https://github.com/optiland/optiland">Optiland</a>, and the lens-level design tool
  <a href="https://github.com/raycrafter-optical-design/raycrafter">RayCrafter</a> built on it,
  reproduce what Zemax OpticStudio gives?</p>
</header>

<section id="about">
  <h2>What this is</h2>
  <p>Each design starts as a Zemax file exported from OpticStudio, together with the plots and numbers
  Zemax produces for it (the reference). We load the same file into Optiland, run the same analyses,
  and compare. Every page puts the verdict first (match, partial or fail, computed from stated
  tolerances), then the evidence: the Zemax output next to ours, then the full Optiland analysis.
  Problems we find in Optiland are written up in
  <a href="https://github.com/raycrafter-optical-design/evaluation/blob/main/optiland_issues_found.md">optiland_issues_found.md</a>,
and each one lists where it stands upstream in <a href="https://github.com/optiland/optiland/issues">optiland/optiland</a> (so far
<a href="https://github.com/optiland/optiland/issues/1210">#1210</a>,
<a href="https://github.com/optiland/optiland/issues/1247">#1247</a>,
<a href="https://github.com/optiland/optiland/issues/1248">#1248</a> and a comment on
<a href="https://github.com/optiland/optiland/issues/865">#865</a>).</p>
  <p>The repository is also where RayCrafter is pointed at designs that largely work in Optiland, with
  the goal that they work in RayCrafter too.</p>
  <p>Each design folder holds the Zemax export, a <code>Zemax_reference_output/</code> folder (what we
  must match), an <code>optiland_analysis/</code> folder (our best attempt, with a README listing every
  file) and the generated page in <code>HTML_summary/</code>.</p>
</section>

<section id="designs">
  <h2>Designs</h2>
  <div class="cards">
@@CARDS@@
  </div>
  <p style="font-size:13px;color:var(--muted)">The counts are the verdicts from each design's Zemax check.
  Once several designs are here we will look for common elements and add a traffic-light summary by
  feature (ray tracing, footprints, spot size, wavefront, distortion, and so on).</p>
</section>

<footer>Generated @@DATE@@ by <code>evaluation_tools/build_summary.py</code>.
<a href="https://github.com/raycrafter-optical-design/evaluation">Source on GitHub</a>.</footer>
</main>
</div>
</body>
</html>
"""


def card_html(entry: dict) -> str:
    """One design card for the landing page."""
    design = entry["design"]
    link = f"designs/{entry['dir_name']}/HTML_summary/index.html"
    return (
        f'    <div class="card"><h3><a href="{html.escape(link)}">{html.escape(design["title"])}</a></h3>\n'
        f"      <p>{html.escape(design['summary'])}</p>\n"
        f"      <p>RayCrafter: {html.escape(design.get('raycrafter', 'not yet tried'))}</p>\n"
        f'      <div class="tally">{tally_html(entry["counts"])}</div></div>'
    )


def build_landing(entries: list[dict], root: Path) -> None:
    """Write ``index.html`` in the repository root."""
    page = LANDING_TEMPLATE.replace("@@CARDS@@", "\n".join(card_html(e) for e in entries)).replace(
        "@@DATE@@", date.today().isoformat()
    )
    (root / "index.html").write_text(page, encoding="utf-8")


def main(root: Path = REPO_ROOT) -> None:
    """Rebuild every design page and the landing page."""
    entries = []
    for design_dir in sorted((root / "designs").iterdir()):
        if (design_dir / "design.json").exists():
            entries.append(build_design(design_dir))
            print("wrote", design_dir / "HTML_summary" / "index.html")
    build_landing(entries, root)
    print("wrote", root / "index.html")


if __name__ == "__main__":
    main()
