"""Generic Optiland analysis of a Zemax design, for designs without a bespoke script.

Usage::

    uv run python -m evaluation_tools.analyze_zmx designs/twinkle_excitation

Writes ``optiland_analysis/results.json``, figures in ``optiland_analysis/figs/`` and the
generated ``comparison.json`` (the verdict rows) next to ``design.json``.

What Zemax gives us to compare with is whatever is stored in the ``.ZMX`` itself, plus any plots
in ``Zemax_reference_output/``. The ZMX stores, for every surface whose semi-diameter is
"automatic", the value Zemax computed from its own ray trace. We re-trace with Optiland and
compare the largest ray radius on each of those surfaces. That checks the geometry, tilts,
glasses and ray tracing of the whole chain, surface by surface.
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from evaluation_tools import analyze, digitise_svg
from evaluation_tools.analyze import local_xy, to_np
from evaluation_tools.load_system import load
from evaluation_tools.zemax_text import configuration_values, galvo_surface_index

COLOURS = ["#1f77b4", "#2ca02c", "#d62728", "#9467bd", "#ff7f0e"]
SD_TOLERANCE = 0.005  # relative; a match
SD_PARTIAL = 1.05  # largest ratio still counted as partial


# ------------------------------------------------------------------ Zemax file ---
def parse_zemax_surfaces(text: str) -> list[dict]:
    """Read the per-surface data we need from UTF-8 ``.zmx`` text, coordinate breaks excluded.

    Each entry has the Zemax surface number, comment, type, radius and thickness (mm),
    glass, semi-diameter ``diam_mm`` with ``diam_is_automatic`` (computed by Zemax, not typed
    in) and ``clear_aperture_mm`` (circular clipping aperture, if any).
    """
    surfaces = []
    for block in re.split(r"(?m)^(?=SURF \d+)", text)[1:]:

        def field(name: str, block: str = block) -> str | None:
            match = re.search(rf"(?m)^\s+{name} (.*)$", block)
            return match.group(1).strip() if match else None

        surface_type = field("TYPE") or ""
        if surface_type == "COORDBRK":
            continue
        curvature = float((field("CURV") or "0").split()[0])
        diam = (field("DIAM") or "0 0").split()
        glass = (field("GLAS") or "").split()
        aperture = field("CLAP") or field("FLAP")
        surfaces.append(
            {
                "zemax": int(re.match(r"SURF (\d+)", block).group(1)),
                "comment": field("COMM") or "",
                "type": surface_type,
                "radius_mm": 1.0 / curvature if curvature else None,
                "thickness_mm": float(field("DISZ"))
                if field("DISZ") not in (None, "INFINITY")
                else None,
                "glass": glass[0] if glass else "",
                "diam_mm": float(diam[0]),
                "diam_is_automatic": diam[1] == "0",
                "clear_aperture_mm": float(aperture.split()[1]) if aperture else None,
                "is_stop": bool(re.search(r"(?m)^\s+STOP\s*$", block)),
            }
        )
    return surfaces


def tilt_configurations(text: str) -> list[float]:
    """Galvo angles of the multi-configuration table, in file order (empty if single-config)."""
    return configuration_values(text) if galvo_surface_index(text) is not None else []


# ------------------------------------------------------------------- tracing ---
def field_fractions(op) -> tuple[list[float], list[float]]:
    """Field angles (deg) in the file and their normalised Hy coordinates for ``op.trace``."""
    angles = [float(f.y) for f in op.fields.fields]
    largest = max(abs(a) for a in angles) or 1.0
    return angles, [a / largest for a in angles]


def trace_local(op, hy: float, wavelength_um: float, num_rings: int = 24) -> np.ndarray:
    """Trace a hexapolar pupil; return local (x, y) per surface, shape (surfaces, 2, rays).

    The object surface (index 0) is at infinity, so its row is zeros.
    """
    op.trace(0.0, hy, wavelength_um, num_rings, "hexapolar")
    rows = [np.zeros((2, len(to_np(op.surfaces[1].x))))]
    rows += [np.stack(local_xy(op, index)) for index in range(1, len(op.surfaces))]
    return np.stack(rows)


MIN_SEMI_DIAMETER_MM = 1e-3  # below this the "surface" is a focus; a ratio means nothing


def semi_diameter_check(
    op, zemax_surfaces: list[dict], hy_values: list[float], excluded: dict[str, str]
) -> list[dict]:
    """Largest local ray radius per automatic-semi-diameter surface, against Zemax's value.

    ``excluded`` maps a Zemax surface number (as text) to the reason it is not scored; such
    rows are kept, with ``excluded_reason`` set, so the page can show them.
    """
    wavelengths = [w.value for w in op.wavelengths.wavelengths]
    peak = np.zeros(len(op.surfaces))
    for hy in hy_values:
        for wavelength in wavelengths:
            local = trace_local(op, hy, wavelength, num_rings=40)
            radius = np.hypot(local[:, 0], local[:, 1])
            peak = np.fmax(peak, np.nanmax(radius, axis=1))
    rows = []
    for optiland_index, surface in enumerate(zemax_surfaces):
        if surface["diam_is_automatic"] and surface["diam_mm"] > MIN_SEMI_DIAMETER_MM:
            rows.append(
                {
                    "excluded_reason": excluded.get(str(surface["zemax"])),
                    "zemax_surface": surface["zemax"],
                    "optiland_surface": optiland_index,
                    "comment": surface["comment"],
                    "zemax_mm": surface["diam_mm"],
                    "optiland_mm": float(peak[optiland_index]),
                }
            )
    return rows


def image_numerical_aperture(op, wavelength_um: float) -> float:
    """Image-space NA from the real marginal ray, in the image surface's local frame."""
    return analyze.image_na(op, wavelength_um)


def spot_data(op, hy: float, wavelength_um: float) -> dict:
    """Image-plane spot for one field: local coordinates (µm), centroid, RMS radius, survivors."""
    op.trace(0.0, hy, wavelength_um, 24, "hexapolar")
    x_mm, y_mm = local_xy(op, len(op.surfaces) - 1)
    good = np.isfinite(x_mm) & np.isfinite(y_mm)
    chief_x, chief_y = x_mm[0], y_mm[0]  # first ray of a hexapolar pattern is the chief ray
    centroid_x, centroid_y = np.mean(x_mm[good]), np.mean(y_mm[good])
    rms_um = 1e3 * float(
        np.sqrt(np.mean((x_mm[good] - centroid_x) ** 2 + (y_mm[good] - centroid_y) ** 2))
    )
    return {
        "x_um": (1e3 * x_mm[good]).tolist(),
        "y_um": (1e3 * y_mm[good]).tolist(),
        "chief_x_mm": float(chief_x),
        "chief_y_mm": float(chief_y),
        "rms_um": rms_um,
        "rays_reaching_image": int(good.sum()),
    }


def transmission_vs_field(op, hy_values: list[float]) -> list[float]:
    """Fraction of pupil rays that survive Optiland's imported Zemax apertures, per field.

    Optiland clips by setting a ray's intensity to zero (the ray itself stays finite), so
    the survivors are the rays with non-zero intensity on the last surface.
    """
    wavelength = op.wavelengths.primary_wavelength.value
    fractions = []
    for hy in hy_values:
        op.trace(0.0, hy, wavelength, 40, "hexapolar")
        fractions.append(float(np.mean(to_np(op.surfaces[-1].intensity) > 0)))
    return fractions


# ------------------------------------------------------------------- figures ---
def layout_fields(hy_values: list[float]) -> list[float]:
    """Smallest, middle (0) and largest normalised field, so the layout stays readable."""
    chosen = {min(hy_values), max(hy_values)} | ({0.0} if 0.0 in hy_values else set())
    return sorted(chosen)


def layout_figure(op, hy_values: list[float], results: dict, title: str) -> None:
    """Ray paths in the plane of the system, from Optiland's own global ray coordinates.

    Optiland's ``op.draw`` is not usable here: it plots every surface in the global y-z plane
    and so mangles tilted or folded systems. We project the global ray points onto the plane
    that best fits the chief-ray path (principal axes of the path points).
    """
    primary = op.wavelengths.primary_wavelength.value
    paths, mirror_points = [], []
    for hy in hy_values:
        op.trace(0.0, hy, primary, 1, "hexapolar")
        points = np.stack(
            [np.stack([to_np(s.x), to_np(s.y), to_np(s.z)]) for s in op.surfaces[1:]]
        )  # (surfaces, xyz, rays)
        paths.append(points)
        for index, surface in enumerate(op.surfaces[1:]):
            if surface.interaction_model.is_reflective and hy == hy_values[0]:
                mirror_points.append(points[index, :, 0])
    chief = np.stack([path[:, :, 0] for path in paths]).reshape(-1, 3)
    chief = chief[np.isfinite(chief).all(axis=1)]
    centre = chief.mean(axis=0)
    axes = np.linalg.svd(chief - centre)[2][:2]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for k, points in enumerate(paths):
        for ray in range(points.shape[2]):
            xy = (points[:, :, ray] - centre) @ axes.T
            ax.plot(xy[:, 0], xy[:, 1], lw=0.6, color=COLOURS[k % len(COLOURS)], alpha=0.8)
    for point in mirror_points:
        xy = (point - centre) @ axes.T
        ax.plot(xy[0], xy[1], "ks", ms=6)
    all_points = np.concatenate(
        [((p.transpose(0, 2, 1) - centre) @ axes.T).reshape(-1, 2) for p in paths]
    )
    all_points = all_points[np.isfinite(all_points).all(axis=1)]
    spans = np.ptp(all_points, axis=0)
    if spans[0] < 4 * spans[1]:
        ax.set_aspect("equal")
        ax.set_ylabel("perpendicular (mm)")
    else:  # a long thin system: equal aspect would be unreadable
        ax.set_ylabel("perpendicular (mm), scale exaggerated")
    ax.set_xlabel("position along the main axis of the system (mm)")
    ax.set_title(title + " (black squares: mirrors)")
    ax.grid(alpha=0.3)
    results["figs"]["layout_rays"] = analyze.save(fig, "layout_rays")


def spot_figure(
    spots: dict[str, dict], reference: dict, name: str, results: dict, title: str
) -> None:
    """Spot diagrams side by side, each centred on its centroid, on one common scale.

    The dashed circle is the reference radius (Airy, or the Zemax image-plane aperture).
    """
    radius_um = reference["radius_um"]
    centred = {}
    for label, spot in spots.items():
        x, y = np.array(spot["x_um"]), np.array(spot["y_um"])
        centred[label] = (x - x.mean(), y - y.mean(), spot["rms_um"])
    extent = max(max(np.abs(x).max(), np.abs(y).max()) for x, y, _ in centred.values())
    extent = max(extent, radius_um) * 1.15
    columns = min(len(centred), 6)
    rows = int(np.ceil(len(centred) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(2.6 * columns, 2.7 * rows), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, (label, (x, y, rms_um)) in zip(axes.ravel(), centred.items()):
        ax.axis("on")
        ax.scatter(x, y, s=2, color=COLOURS[0])
        ax.add_patch(plt.Circle((0, 0), radius_um, fill=False, ls="--", color="k", lw=0.8))
        ax.set_xlim(-extent, extent)
        ax.set_ylim(-extent, extent)
        ax.set_aspect("equal")
        ax.set_title(f"{label}\nRMS {rms_um:.3g} µm", fontsize=8)
        ax.tick_params(labelsize=6)
    fig.suptitle(
        f"{title} (dashed circle: {reference['label']} {radius_um:.4g} µm; axes in µm)", fontsize=9
    )
    fig.tight_layout()
    results["figs"][name] = analyze.save(fig, name)


def relative_illumination_figure(data: dict, results: dict) -> None:
    """Zemax relative illumination (digitised) against Optiland's unvignetted pupil fraction."""
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(
        data["field_deg"], data["zemax_ri"], "-", color=COLOURS[0], label="Zemax RI (digitised)"
    )
    ax.plot(
        data["fine_field_deg"],
        data["fine_fraction"],
        "--",
        color=COLOURS[2],
        label="Optiland: fraction of pupil rays inside all apertures",
    )
    ax.set_xlabel("Field angle (deg)")
    ax.set_ylabel("Relative illumination / pupil fraction")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    results["figs"]["relative_illumination"] = analyze.save(fig, "relative_illumination")


def zemax_scan_figure(curves: dict, results: dict) -> None:
    """The three Zemax angle-scan curves (digitised), for reference beside the Optiland scan."""
    fig, axes = plt.subplots(3, 1, figsize=(7.5, 7), sharex=True)
    series = [
        ("axial_peak_offset_um", "Axial peak offset (µm)", None),
        ("radial_fwhm_um", "Radial FWHM, 2-photon (µm)", 0.75),
        ("axial_fwhm_um", "Axial FWHM, 2-photon (µm)", 5.0),
    ]
    for ax, (key, label, target) in zip(axes, series):
        ax.plot(curves["angle_deg"], curves[key], "o", ms=4, color=COLOURS[0])
        if target:
            ax.axhline(target, color="k", ls="--", lw=1)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("Galvo angle (deg)")
    axes[0].set_title(
        "Zemax (digitised from the MATLAB plot); dashed: the authors' targets", fontsize=9
    )
    results["figs"]["zemax_scan_curves"] = analyze.save(fig, "zemax_scan_curves")


def rms_figure(
    angles: list[float], rms_um: list[float], reference: dict, results: dict, xlabel: str
) -> None:
    """RMS spot radius against scan angle or field, with a reference radius."""
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(angles, rms_um, "o-", color=COLOURS[0], label="RMS spot radius (geometric)")
    ax.axhline(
        reference["radius_um"],
        color="k",
        ls="--",
        lw=1,
        label=f"{reference['label']} {reference['radius_um']:.4g} µm",
    )
    ax.set_xlabel(xlabel)
    ax.set_ylabel("RMS spot radius (µm)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    results["figs"]["rms_spot"] = analyze.save(fig, "rms_spot")


def chief_ray_figure(angles: list[float], position_mm: list[float], results: dict) -> None:
    """Chief-ray position on the image plane against galvo angle, with a straight-line fit."""
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(angles, np.array(position_mm) * 1e3, "o", color=COLOURS[0], label="Optiland")
    slope, offset = np.polyfit(angles, np.array(position_mm) * 1e3, 1)
    ax.plot(
        angles,
        slope * np.array(angles) + offset,
        "k--",
        lw=1,
        label=f"straight line, {slope:.1f} µm per degree",
    )
    ax.set_xlabel("Galvo angle (deg)")
    ax.set_ylabel("Chief-ray position on image plane (µm)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    results["figs"]["chief_ray_position"] = analyze.save(fig, "chief_ray_position")


# --------------------------------------------------------------------- driver ---
def lens_table(op, zemax_surfaces: list[dict]) -> list[dict]:
    """Prescription as Zemax states it, with Optiland's radius next to it for checking."""
    rows = []
    for optiland_index, surface in enumerate(zemax_surfaces):
        optiland_radius = float(
            to_np(getattr(op.surfaces[optiland_index].geometry, "radius", np.inf))
        )
        rows.append(
            {
                **surface,
                "optiland_radius_mm": optiland_radius if np.isfinite(optiland_radius) else None,
                "is_mirror": surface["glass"] == "MIRROR",
            }
        )
    return rows


def write_comparison(design_dir: Path, results: dict) -> None:
    """Write ``comparison.json``: one verdict row per automatic semi-diameter."""
    rows = []
    for index, check in enumerate(results["semi_diameter_check"]):
        if check["excluded_reason"]:
            continue
        rows.append(
            {
                "id": f"sd_{check['zemax_surface']}",
                "label": f"Semi-diameter, surface {check['zemax_surface']}"
                + (f" ({check['comment']})" if check["comment"] else "")
                + " (mm)",
                "zemax": [check["zemax_mm"]],
                "zemax_source": "DIAM stored in the .ZMX (computed by Zemax)",
                "optiland": [f"results.json:semi_diameter_check/{index}/optiland_mm"],
                "mode": "ratio",
                "tol": SD_TOLERANCE,
                "partial_tol": SD_PARTIAL,
                "decimals": 4,
            }
        )
    for index, row in enumerate(results.get("zemax_plot_checks", [])):
        rows.append(
            {**row["comparison"], "optiland": [f"results.json:zemax_plot_checks/{index}/optiland"]}
        )
    comparison = {
        "description": "Rows of the verdict table, generated by analyze_zmx.py. Semi-diameter rows "
        "compare the DIAM Zemax stored for automatic-semi-diameter surfaces with the largest "
        "local ray radius Optiland finds (ratio mode: match within 0.5%, partial within 5%).",
        "rows": rows,
    }
    (design_dir / "comparison.json").write_text(json.dumps(comparison, indent=1), encoding="utf-8")


def probe_wavefront(op, wavelength_um: float) -> dict:
    """Can Optiland's FFT PSF (and so Strehl and wavefront error) run on this system?"""
    from optiland.psf import FFTPSF

    try:
        strehl = FFTPSF(op, field=(0, 0), wavelength=wavelength_um, num_rays=64, grid_size=256)
        return {"works": True, "on_axis_strehl": float(strehl.strehl_ratio())}
    except Exception as error:  # noqa: BLE001 - the failure is the finding
        return {
            "works": False,
            "error": f"{type(error).__name__}: {str(error).splitlines()[0][:160]}",
        }


def spot_reference(op, zemax_surfaces: list[dict], primary_um: float) -> dict:
    """Circle drawn on the spot plots: the image-plane clear aperture if Zemax set one, else Airy."""
    aperture = zemax_surfaces[-1]["clear_aperture_mm"]
    if aperture is not None:
        return {
            "kind": "aperture",
            "label": "Zemax image-plane aperture radius",
            "radius_um": 1e3 * aperture,
        }
    na = image_numerical_aperture(op, primary_um)
    return {
        "kind": "airy",
        "label": "Airy radius",
        "radius_um": 0.61 * primary_um / na,
        "image_NA": na,
    }


def scan_galvo(
    zmx_path: Path, work_dir: Path, text: str, primary: float, reference: dict, results: dict
) -> dict[str, dict]:
    """Trace every galvo configuration; fill ``results['scan']`` and its figures; return spots."""
    unique = sorted(set(tilt_configurations(text)))
    results["configurations"] = {"as_in_file": tilt_configurations(text), "unique": unique}
    scan: dict[str, list] = {
        "angle_deg": [],
        "chief_x_mm": [],
        "chief_y_mm": [],
        "rms_um": [],
        "rays": [],
    }
    spots: dict[str, dict] = {}
    for k, angle in enumerate(unique):
        data = spot_data(
            load(zmx_path, work_dir, galvo_angle_deg=angle, suffix=f"_cfg{k}"), 0.0, primary
        )
        for key, value in (
            ("angle_deg", angle),
            ("chief_x_mm", data["chief_x_mm"]),
            ("chief_y_mm", data["chief_y_mm"]),
            ("rms_um", data["rms_um"]),
            ("rays", data["rays_reaching_image"]),
        ):
            scan[key].append(value)
        if angle in (-10, -5, 0, 5, 10) or len(unique) <= 6:
            spots[f"galvo {angle:+g}°"] = data
    results["scan"] = scan
    rms_figure(scan["angle_deg"], scan["rms_um"], reference, results, "Galvo angle (deg)")
    larger_in_y = max(map(abs, scan["chief_y_mm"])) > max(map(abs, scan["chief_x_mm"]))
    chief_ray_figure(
        scan["angle_deg"], scan["chief_y_mm" if larger_in_y else "chief_x_mm"], results
    )
    return spots


def scan_fields(
    op, angles: list[float], hy_values: list[float], primary: float, reference: dict, results: dict
) -> dict[str, dict]:
    """Trace every field of a single-configuration design; return the spots."""
    rows, spots = [], {}
    for angle, hy in zip(angles, hy_values):
        data = spot_data(op, hy, primary)
        rows.append(
            {
                "field_deg": angle,
                "rms_um": data["rms_um"],
                "chief_y_mm": data["chief_y_mm"],
                "rays_reaching_image": data["rays_reaching_image"],
            }
        )
        spots[f"field {angle:+g}°"] = data
    rows.sort(key=lambda row: row["field_deg"])
    results["field_scan"] = rows
    rms_figure(
        [r["field_deg"] for r in rows],
        [r["rms_um"] for r in rows],
        reference,
        results,
        "Field angle (deg)",
    )
    return dict(sorted(spots.items(), key=lambda item: float(item[0].split()[1].rstrip("°"))))


def interpolate_crossing(x: list[float], y: list[float], level: float) -> float:
    """First x where the curve ``y`` falls to ``level`` (linear interpolation), else the last x."""
    for i in range(1, len(x)):
        if y[i] <= level < y[i - 1]:
            return x[i - 1] + (x[i] - x[i - 1]) * (y[i - 1] - level) / (y[i - 1] - y[i])
    return x[-1]


def relative_illumination_checks(op, design_dir: Path, results: dict) -> None:
    """Compare Optiland's unvignetted pupil fraction with Zemax's relative-illumination plot.

    Zemax's curve includes sampling ripple of a few percent and cos-law terms, so we compare
    where the curve falls through 50 % and reaches zero, plus the mean difference.
    """
    svg = design_dir / "Zemax_reference_output" / "RelativeIllumination.svg"
    if not svg.exists():
        return
    curve = digitise_svg.relative_illumination_curve(svg)
    largest = max(abs(a) for a in results["fields_deg"])
    fractions = transmission_vs_field(op, [a / largest for a in curve["field_deg"]])
    fine = list(np.arange(0, largest + 1e-9, 0.1))
    fine_fraction = transmission_vs_field(op, [a / largest for a in fine])
    zemax_ri = curve["relative_illumination"]
    results["relative_illumination"] = {
        "field_deg": curve["field_deg"],
        "zemax_ri": zemax_ri,
        "optiland_fraction": fractions,
        "fine_field_deg": fine,
        "fine_fraction": fine_fraction,
    }
    checks = [
        (
            "ri_half",
            "Field angle where relative illumination falls to 50% (deg)",
            interpolate_crossing(curve["field_deg"], zemax_ri, 0.5),
            interpolate_crossing(fine, fine_fraction, 0.5),
            0.3,
            0.8,
        ),
        (
            "ri_zero",
            "Field angle where relative illumination reaches 0 (deg)",
            interpolate_crossing(curve["field_deg"], zemax_ri, 0.01),
            interpolate_crossing(fine, fine_fraction, 0.01),
            0.3,
            0.8,
        ),
    ]
    mean_difference = float(np.mean(np.abs(np.array(zemax_ri) - np.array(fractions))))
    checks.append(
        (
            "ri_mean",
            "Mean |Zemax RI − Optiland pupil fraction|, 0 to 12° (21 points)",
            0.0,
            mean_difference,
            0.03,
            0.08,
        )
    )
    relative_illumination_figure(results["relative_illumination"], results)
    results["zemax_plot_checks"] = []
    for check_id, label, zemax_value, optiland_value, tol, partial in checks:
        results["zemax_plot_checks"].append(
            {
                "optiland": optiland_value,
                "comparison": {
                    "id": check_id,
                    "label": label,
                    "zemax": [zemax_value],
                    "zemax_source": "RelativeIllumination.svg, read from the plot vector data (digitised)",
                    "mode": "abs",
                    "tol": tol,
                    "partial_tol": partial,
                    "decimals": 2,
                },
            }
        )


def digitise_scan_curves(design_dir: Path, results: dict) -> None:
    """Store the Zemax angle-scan curves (excitation designs) in ``zemax_digitised.json``."""
    svg = design_dir / "Zemax_reference_output" / "FieldCurvatureAndFWHM_vs_angle.svg"
    if svg.exists():
        curves = digitise_svg.scan_curves(svg)
        curves["note"] = (
            "Read from the vector markers of FieldCurvatureAndFWHM_vs_angle.svg. "
            "Digitised, not Zemax numeric output. Radial and axial FWHM are of the "
            "two-photon PSF (Huygens PSF squared)."
        )
        results["zemax_scan"] = curves
        zemax_scan_figure(curves, results)


def main(design_dir: Path) -> None:
    """Run the whole analysis for ``design_dir`` (which holds one ``.ZMX``)."""
    warnings.filterwarnings("ignore")
    analyze.configure(design_dir)
    work_dir, zmx_path = analyze.OUT, analyze.ZMX_SOURCE
    text = zmx_path.read_text(encoding="utf-16")
    zemax_surfaces = parse_zemax_surfaces(text)
    design = json.loads((design_dir / "design.json").read_text(encoding="utf-8"))

    op = load(zmx_path, work_dir)
    angles, hy_values = field_fractions(op)
    primary = op.wavelengths.primary_wavelength.value
    results: dict = {
        "figs": {},
        "zmx": zmx_path.name,
        "wavelengths_um": [w.value for w in op.wavelengths.wavelengths],
        "primary_um": primary,
        "fields_deg": angles,
        "EPD_mm": float(op.aperture.value),
        "surfaces_zemax": len(zemax_surfaces),
        "surfaces_optiland": len(op.surfaces),
        "lens_table": lens_table(op, zemax_surfaces),
        "wavefront": probe_wavefront(op, primary),
    }
    try:
        results["EFL_mm"] = float(to_np(op.paraxial.f2()))
    except Exception as error:  # noqa: BLE001 - recorded as a finding, not a crash
        results["EFL_mm"] = None
        results["paraxial_error"] = str(error).splitlines()[0][:200]

    results["semi_diameter_check"] = semi_diameter_check(
        op, zemax_surfaces, hy_values, design.get("semi_diameter_excluded", {})
    )
    results["transmission_vs_field"] = {
        "field_deg": angles,
        "fraction": transmission_vs_field(op, hy_values),
    }
    layout_figure(op, layout_fields(hy_values), results, f"{design['title']}: Optiland ray paths")

    reference = spot_reference(op, zemax_surfaces, primary)
    results["spot_reference"] = reference
    if tilt_configurations(text):
        spots = scan_galvo(zmx_path, work_dir, text, primary, reference, results)
    else:
        spots = scan_fields(op, angles, hy_values, primary, reference, results)
    spot_figure(spots, reference, "spots", results, "Optiland spot diagrams, primary wavelength")

    relative_illumination_checks(op, design_dir, results)
    digitise_scan_curves(design_dir, results)
    try:
        analyze.export_3d(op, results)
    except Exception as error:  # noqa: BLE001 - recorded, the page then omits the viewer
        results["glb_error"] = str(error)[:200]

    # Keep only what a reader needs: the per-configuration .zmx copies are scratch, and the 3D
    # model is only worth its size on pages that embed the interactive viewer.
    for scratch in work_dir.glob("*_cfg*_utf8.zmx"):
        scratch.unlink()
    if not design.get("viewer"):
        (work_dir / "model.glb").unlink(missing_ok=True)
    digitised = {}
    if "zemax_scan" in results:
        digitised["zemax_scan"] = results["zemax_scan"]
    if "relative_illumination" in results:
        ri = results["relative_illumination"]
        digitised["relative_illumination"] = {
            "field_deg": ri["field_deg"],
            "relative_illumination": ri["zemax_ri"],
            "note": "Read from the vertices of RelativeIllumination.svg. Digitised, not Zemax numeric output.",
        }
    if digitised:
        digitised_path = design_dir / "Zemax_reference_output" / "zemax_digitised.json"
        digitised_path.write_text(json.dumps(digitised, indent=1), encoding="utf-8")
    (analyze.OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    write_comparison(design_dir, results)
    print("wrote", analyze.OUT / "results.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
