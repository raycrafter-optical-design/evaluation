"""Run optiland analyses on the SMOD4.5 scan system and write figures + JSON.

Usage:  uv run python -m evaluation_tools.analyze designs/SMOD4.5
Outputs go to <design>/optiland_analysis/ (figures in figs/, numbers in results.json).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import ConvexHull

from evaluation_tools.load_system import load

# Set by configure(); the analyses write their figures here.
OUT = Path("optiland_analysis")
FIGS = OUT / "figs"
ZMX_SOURCE = Path()
BA = 19  # optiland index of the back aperture (Zemax surface 21, paraxial f=12.5)
WL_COLORS = {0.85: "#1f77b4", 0.94: "#2ca02c", 1.1: "#d62728"}

plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 130, "font.size": 10})


def configure(design_dir: Path) -> None:
    """Point the module at ``design_dir``: its single .ZMX in, ``optiland_analysis/`` out."""
    global OUT, FIGS, ZMX_SOURCE
    matches = sorted(p for p in design_dir.iterdir() if p.suffix.lower() == ".zmx")
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one .ZMX in {design_dir}, found {len(matches)}")
    ZMX_SOURCE = matches[0]
    OUT = design_dir / "optiland_analysis"
    FIGS = OUT / "figs"


def save(fig, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    return f"figs/{name}.png"


def to_np(a):
    from optiland import backend as be

    return np.asarray(be.to_numpy(a), dtype=float)


def local_xy(op, idx: int):
    """Ray intersection points on surface ``idx`` in that surface's local frame."""
    s = op.surfaces[idx]
    cs = s.geometry.cs
    R = to_np(cs.get_rotation_matrix())
    origin = np.array([to_np(c).ravel()[0] for c in cs.position_in_gcs])
    p = np.stack([to_np(s.x), to_np(s.y), to_np(s.z)], axis=1) - origin
    loc = p @ R  # R^T (p - o) for row vectors
    return loc[:, 0], loc[:, 1]


def max_field_deg(op) -> float:
    return float(max(abs(f.y) for f in op.fields.fields))


# --------------------------------------------------------------------- data ---
def zemax_surface_comments(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-16")
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"SURF (\d+)", line)
        if m:
            cur = int(m.group(1))
        m = re.match(r"\s+COMM (.*)", line)
        if m and cur is not None:
            out[cur] = m.group(1).strip()
    return out


def lens_table(op) -> list[dict]:
    """Prescription with Zemax comments re-attached (optiland drops COMM).

    optiland folds the two COORDBRK surfaces (Zemax 17, 19) into the
    neighbouring surfaces' coordinate systems, so indices shift by up to two.
    """
    comments = zemax_surface_comments(ZMX_SOURCE)
    zmx_index = [i for i in range(23) if i not in (17, 19)]
    wls = [w.value for w in op.wavelengths.wavelengths]
    rows = []
    for i, s in enumerate(op.surfaces):
        g = s.geometry
        r = float(to_np(getattr(g, "radius", np.inf)))
        mat = s.material_post
        name = getattr(mat, "name", None) or type(mat).__name__.replace("Material", "")
        if name in ("Ideal", "IdealMaterial"):
            name = "Air"
        if s.interaction_model.is_reflective:
            name = "MIRROR"
        try:
            n = [round(float(to_np(mat.n(w)).ravel()[0]), 5) for w in wls]
        except Exception:
            n = None
        im = s.interaction_model
        kind = (
            f"Paraxial f={float(im.f):g}"
            if type(im).__name__ == "ThinLensInteractionModel"
            else ("Mirror" if im.is_reflective else type(g).__name__.replace("Geometry", ""))
        )
        zi = zmx_index[i]
        rows.append(
            {
                "optiland": i,
                "zemax": zi,
                "comment": comments.get(zi, ""),
                "type": kind,
                "radius": None if not np.isfinite(r) else round(r, 3),
                "material": name,
                "n": n,
                "semi_ap": round(float(to_np(s.semi_aperture)), 3)
                if s.semi_aperture is not None
                else None,
                "stop": bool(getattr(s, "is_stop", False)),
            }
        )
    # thickness from the prescription (axial spacing to next surface, signed)
    for i, row in enumerate(rows[:-1]):
        t = float(to_np(op.surfaces.get_thickness(i)).ravel()[0])
        row["thickness"] = round(t, 4) if np.isfinite(t) else None
    return rows


# ------------------------------------------------------------------ analyses --
def layout(op, res):
    fig, ax = op.draw(fields="all", wavelengths="primary", num_rays=5, figsize=(14, 5), show=False)
    res["figs"]["layout_yz"] = save(fig, "layout_yz")
    # Zoom into the end: fold mirror -> objective -> focus
    fig, ax = op.draw(
        fields="all",
        wavelengths="primary",
        num_rays=7,
        figsize=(8, 6),
        show=False,
        xlim=(440, 520),
        ylim=(-15, 175),
    )
    res["figs"]["layout_fold"] = save(fig, "layout_fold")


def back_aperture_footprint(op, res):
    """Footprint on the objective back aperture, every field x wavelength."""
    wls = [w.value for w in op.wavelengths.wavelengths]
    fmax = max_field_deg(op)
    Hy_list = [-1, -0.7, -0.35, 0, 0.35, 0.7, 1]
    zmx_ba_semi = 10.0

    fig, axes = plt.subplots(1, len(wls), figsize=(5 * len(wls), 5), sharey=True)
    cmap = plt.get_cmap("viridis")
    summary = {}
    for ax, w in zip(axes, wls):
        rows = []
        for k, Hy in enumerate(Hy_list):
            op.trace(0, Hy, w, 1500, "uniform")
            x, y = local_xy(op, BA)
            c = cmap(k / (len(Hy_list) - 1))
            ok = np.isfinite(x) & np.isfinite(y)
            hull = ConvexHull(np.c_[x[ok], y[ok]])
            hv = np.r_[hull.vertices, hull.vertices[:1]]
            ax.plot(x[ok][hv], y[ok][hv], color=c, lw=1.3)
            r = np.hypot(x - x.mean(), y - y.mean())
            rows.append(
                {
                    "Hy": Hy,
                    "deg": Hy * fmax,
                    "cx": x.mean(),
                    "cy": y.mean(),
                    "radius": r.max(),
                    "max_r_from_axis": np.hypot(x, y).max(),
                }
            )
        for k, row in enumerate(rows):
            ax.plot(row["cx"], row["cy"], "+", color=cmap(k / (len(Hy_list) - 1)), ms=10)
        th = np.linspace(0, 2 * np.pi, 400)
        ax.plot(
            zmx_ba_semi * np.cos(th),
            zmx_ba_semi * np.sin(th),
            "k--",
            lw=1,
            label=f"Back aperture Ø{2 * zmx_ba_semi:g} mm (Zemax DIAM)",
        )
        ax.set_aspect("equal")
        ax.set_title(f"λ = {w} µm")
        ax.set_xlabel("x (mm)")
        ax.grid(alpha=0.3)
        summary[w] = rows
    axes[0].set_ylabel("y (mm)")
    axes[0].legend(loc="lower left", fontsize=8)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-fmax, fmax))
    fig.colorbar(sm, ax=axes, label="Scan angle (deg)", shrink=0.8)
    fig.suptitle("Beam footprint outlines on objective back aperture (+ = centroid)")
    res["figs"]["ba_footprint"] = save(fig, "ba_footprint")

    # Conjugation check: footprint centroid walk vs scan angle, and where the
    # chief rays actually cross the axis (the true galvo image) in BA space.
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    Hy_fine = np.linspace(0, 1, 21)
    conj = {}
    for w in wls:
        walk = []
        for Hy in Hy_fine:
            op.trace(0, Hy, w, 800, "uniform")
            x, y = local_xy(op, BA)
            walk.append(y.mean())
        walk = np.array(walk)
        a1.plot(Hy_fine * fmax, walk, "-o", ms=3, color=WL_COLORS.get(w), label=f"{w} µm")
        conj[w] = {"deg": (Hy_fine * fmax).tolist(), "walk_mm": walk.tolist()}
    a1.set_xlabel("Scan angle (deg)")
    a1.set_ylabel("Footprint centroid shift on BA (mm)")
    a1.set_title("Pupil walk at the back aperture (0 = perfectly conjugate)")
    a1.grid(alpha=0.3)
    a1.legend()

    # Location of the galvo (stop) image relative to BA: trace chief rays and
    # find where they cross the axis, using two points in BA-space.
    pos = []
    for w in wls:
        zs = []
        for Hy in np.linspace(0.1, 1, 10):
            op.trace_generic(0, Hy, 0, 0, w)
            s = op.surfaces[BA - 1]  # 'underside of flip cube' (Zemax 20)
            L, M, N = (to_np(s.L)[0], to_np(s.M)[0], to_np(s.N)[0])
            _, hb = local_xy(op, BA)
            R = to_np(op.surfaces[BA].geometry.cs.get_rotation_matrix())
            d = np.array([L, M, N]) @ R  # direction in BA frame
            # distance along BA axis (positive = towards objective/sample side)
            zs.append(-hb[0] / (d[1] / d[2]) * np.sign(d[2]))
        pos.append(np.array(zs))
        a2.plot(
            np.linspace(0.1, 1, 10) * fmax, zs, "-o", ms=3, color=WL_COLORS.get(w), label=f"{w} µm"
        )
    a2.axhline(0, color="k", lw=0.8)
    a2.set_xlabel("Scan angle (deg)")
    a2.set_ylabel("Axial position of galvo image\nrelative to BA (mm)")
    a2.set_title("Where the chief rays cross the axis")
    a2.grid(alpha=0.3)
    a2.legend()
    fig.tight_layout()
    res["figs"]["ba_conjugation"] = save(fig, "ba_conjugation")
    res["ba"] = {
        "footprint": {str(k): v for k, v in summary.items()},
        "walk": {str(k): v for k, v in conj.items()},
        "galvo_image_offset_mm": {str(w): float(np.median(p)) for w, p in zip(wls, pos)},
    }


def zemax_comparison_numbers(op, res):
    """Numbers that Zemax prints on its footprint diagrams, for comparison.

    Zemax uses a 60-ring hexapolar pupil, all wavelengths and the five fields 0, 5, 6.5, 7, 10 deg.
    """
    wls = [w.value for w in op.wavelengths.wavelengths]
    fmax = max_field_deg(op)
    zemax_fields_deg = [0.0, 5.0, 6.5, 7.0, 10.0]
    ba_x, ba_y, img_x, img_y = [], [], [], []
    for deg in zemax_fields_deg:
        for w in wls:
            op.trace(0, deg / fmax, w, 60, "hexapolar")
            bx, by = local_xy(op, BA)
            ba_x.append(bx)
            ba_y.append(by)
            if w == res["primary_um"]:
                ix, iy = local_xy(op, len(op.surfaces) - 1)
                img_x.append(ix)
                img_y.append(iy)
    ba_x, ba_y = np.concatenate(ba_x), np.concatenate(ba_y)
    img_x, img_y = np.concatenate(img_x), np.concatenate(img_y)
    chief_y_mm = {}
    for deg in zemax_fields_deg:
        op.trace_generic(0, deg / fmax, 0, 0, res["primary_um"])
        _, yi = local_xy(op, len(op.surfaces) - 1)
        chief_y_mm[str(deg)] = abs(float(yi[0]))
    res["zemax_comparison"] = {
        "back_aperture_x_max_abs_mm": float(np.nanmax(np.abs(ba_x))),
        "back_aperture_y_min_mm": float(np.nanmin(ba_y)),
        "back_aperture_y_max_mm": float(np.nanmax(ba_y)),
        "image_max_radius_primary_mm": float(np.nanmax(np.hypot(img_x, img_y))),
        "image_x_max_abs_primary_mm": float(np.nanmax(np.abs(img_x))),
        "image_chief_height_mm": chief_y_mm,
    }


def focal_plane_fov(op, res):
    """Chief-ray landing grid for a 2D (x/y galvo) scan and spot clouds."""
    fmax = max_field_deg(op)
    w0 = op.wavelengths.primary_wavelength.value
    n = 11
    H = np.linspace(-1, 1, n)
    fig, a1 = plt.subplots(figsize=(6.5, 6))
    pts = np.zeros((n, n, 2))
    for i, hx in enumerate(H):
        for j, hy in enumerate(H):
            op.trace_generic(hx, hy, 0, 0, w0)
            x, y = local_xy(op, len(op.surfaces) - 1)
            pts[i, j] = x[0] * 1e3, y[0] * 1e3
    for i in range(n):
        a1.plot(pts[i, :, 0], pts[i, :, 1], "-", color="#1f77b4", lw=0.8)
        a1.plot(pts[:, i, 0], pts[:, i, 1], "-", color="#1f77b4", lw=0.8)
    a1.plot(pts[..., 0].ravel(), pts[..., 1].ravel(), ".", color="#1f77b4", ms=3)
    a1.set_aspect("equal")
    a1.set_xlabel("x (µm)")
    a1.set_ylabel("y (µm)")
    a1.set_title(f"Scanned field in focal plane, ±{fmax:g}° in x and y (λ={w0} µm)")
    a1.grid(alpha=0.3)

    fig.tight_layout()
    res["figs"]["fov"] = save(fig, "fov")
    res["fov"] = {
        "x_extent_um": float(pts[..., 0].max() - pts[..., 0].min()),
        "y_extent_um": float(pts[..., 1].max() - pts[..., 1].min()),
        "y_halfheight_um_at_max_field": float(pts[n // 2, -1, 1]),
        "corner_um": pts[-1, -1].tolist(),
    }


def image_na(op, w) -> float:
    op.trace_generic(0, 0, 0, 1, w)
    s = op.surfaces[-1]
    R = to_np(s.geometry.cs.get_rotation_matrix())
    d = np.array([to_np(s.L)[0], to_np(s.M)[0], to_np(s.N)[0]]) @ R
    return float(np.hypot(d[0], d[1]) / np.linalg.norm(d))


def rms_vs_field(op, res):
    from optiland.analysis import RmsSpotSizeVsField, RmsWavefrontErrorVsField

    fmax = max_field_deg(op)
    wls = [w.value for w in op.wavelengths.wavelengths]
    na = {w: image_na(op, w) for w in wls}
    res["image_NA"] = {str(w): na[w] for w in wls}

    spot = RmsSpotSizeVsField(op, num_fields=41, wavelengths="all", num_rings=12)
    s = to_np(spot._spot_size) * 1e3  # mm -> µm, shape (fields, wavelengths)
    deg = to_np(spot._field)[:, 1] * fmax
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for k, w in enumerate(wls):
        ax.plot(deg, s[:, k], color=WL_COLORS.get(w), label=f"{w} µm RMS spot")
        airy = 0.61 * w / na[w]
        ax.axhline(
            airy, color=WL_COLORS.get(w), ls="--", lw=1, label=f"{w} µm Airy radius {airy:.2f} µm"
        )
    ax.set_xlabel("Scan angle (deg)")
    ax.set_ylabel("RMS spot radius (µm)")
    ax.set_title(f"RMS spot radius vs field (image NA ≈ {na[wls[0]]:.3f})")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    res["figs"]["rms_spot"] = save(fig, "rms_spot")

    wfe = RmsWavefrontErrorVsField(op, num_fields=41, wavelengths="all", num_rays=32)
    e = to_np(wfe._wavefront_error)
    deg_w = to_np(wfe._field)[:, 1] * fmax
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for k, w in enumerate(wls):
        ax.plot(deg_w, e[:, k], color=WL_COLORS.get(w), label=f"{w} µm")
    ax.axhline(0.0716, color="k", ls="--", lw=1, label="Maréchal limit λ/14 (Strehl 0.8)")
    ax.set_xlabel("Scan angle (deg)")
    ax.set_ylabel("RMS wavefront error (waves)")
    ax.set_title("RMS wavefront error vs field")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    res["figs"]["rms_wfe"] = save(fig, "rms_wfe")
    res["rms"] = {
        "deg": deg.tolist(),
        "spot_um": {str(w): s[:, k].tolist() for k, w in enumerate(wls)},
        "deg_wfe": deg_w.tolist(),
        "wfe_waves": {str(w): e[:, k].tolist() for k, w in enumerate(wls)},
    }
    return deg_w, e


def strehl_vs_field(op, res, deg_w, wfe):
    from optiland.psf import FFTPSF

    fmax = max_field_deg(op)
    wls = [w.value for w in op.wavelengths.wavelengths]
    Hy = np.linspace(0, 1, 11)
    st = np.zeros((len(Hy), len(wls)))
    for i, h in enumerate(Hy):
        for k, w in enumerate(wls):
            psf = FFTPSF(op, field=(0, float(h)), wavelength=w, num_rays=128, grid_size=512)
            st[i, k] = psf.strehl_ratio()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for k, w in enumerate(wls):
        ax.plot(Hy * fmax, st[:, k], "-o", ms=4, color=WL_COLORS.get(w), label=f"{w} µm (FFT PSF)")
        ax.plot(
            deg_w,
            np.exp(-((2 * np.pi * wfe[:, k]) ** 2)),
            ":",
            color=WL_COLORS.get(w),
            label=f"{w} µm (Maréchal from RMS WFE)",
        )
    ax.axhline(0.8, color="k", ls="--", lw=1, label="Diffraction limited (0.8)")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Scan angle (deg)")
    ax.set_ylabel("Strehl ratio")
    ax.set_title("Strehl ratio vs field")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    res["figs"]["strehl"] = save(fig, "strehl")
    res["strehl"] = {
        "deg": (Hy * fmax).tolist(),
        "fft": {str(w): st[:, k].tolist() for k, w in enumerate(wls)},
    }


def builtin_views(op, res):
    from optiland.analysis import Distortion, FieldCurvature, GridDistortion, SpotDiagram

    fc = FieldCurvature(op, wavelengths="all", num_points=64)
    fig, _ = fc.view(show=False)
    res["figs"]["field_curvature"] = save(fig, "field_curvature")

    d = Distortion(op, wavelengths="all", num_points=64, distortion_type="f-tan")
    fig, _ = d.view(show=False)
    res["figs"]["distortion_ftan"] = save(fig, "distortion_ftan")
    d = Distortion(op, wavelengths="all", num_points=64, distortion_type="f-theta")
    fig, _ = d.view(show=False)
    res["figs"]["distortion_ftheta"] = save(fig, "distortion_ftheta")

    for kind in ("f-tan", "f-theta"):
        g = GridDistortion(op, wavelength="primary", num_points=11, distortion_type=kind)
        fig, _ = g.view(show=False)
        res["figs"][f"grid_{kind}"] = save(fig, f"grid_{kind.replace('-', '')}")
        res.setdefault("grid_max_distortion_pct", {})[kind] = float(
            to_np(g.data["max_distortion"]) if "max_distortion" in g.data else np.nan
        )

    sd = SpotDiagram(op, fields="all", wavelengths="all", num_rings=8)
    fig, _ = sd.view(figsize=(16, 4), add_airy_disk=True, show=False)
    res["figs"]["spots"] = save(fig, "spots")


def export_3d(op, res):
    """Use optiland's own VTK 3D viewer, render offscreen, export glTF + PNG."""
    import vtk
    from optiland.visualization.system.optic_viewer_3d import OpticViewer3D

    v = OpticViewer3D(op)
    ren = v._make_renderer(False)
    v.ren_win.SetOffScreenRendering(1)
    v.ren_win.AddRenderer(ren)
    v.rays.plot(
        ren,
        fields="all",
        wavelengths="all",
        num_rays=12,
        distribution="ring",
        reference=None,
        hide_vignetted=False,
    )
    v.system.plot(ren)
    # optiland meshes each lens face with ~65k vertices; decimate for the web
    actors = ren.GetActors()
    actors.InitTraversal()
    for _ in range(actors.GetNumberOfItems()):
        a = actors.GetNextActor()
        m = a.GetMapper()
        if m is None or m.GetNumberOfInputConnections(0) == 0:
            continue
        tri = vtk.vtkTriangleFilter()
        tri.SetInputConnection(m.GetInputConnection(0, 0))
        tri.Update()
        if tri.GetOutput().GetNumberOfPoints() < 5000:
            continue
        dec = vtk.vtkQuadricDecimation()
        dec.SetInputConnection(tri.GetOutputPort())
        dec.SetTargetReduction(0.97)
        dec.Update()
        clean = vtk.vtkPolyDataNormals()
        clean.SetInputConnection(dec.GetOutputPort())
        clean.Update()
        m.RemoveAllInputConnections(0)
        m.SetInputData(clean.GetOutput())
    v.ren_win.SetSize(1400, 900)
    cam = ren.GetActiveCamera()
    cam.SetPosition(1, 0.6, 0.3)
    cam.SetFocalPoint(0, 0, 0)
    cam.SetViewUp(0, 1, 0)
    ren.ResetCamera()
    v.ren_win.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(v.ren_win)
    w2i.Update()
    png = vtk.vtkPNGWriter()
    png.SetFileName(str(FIGS / "layout_3d.png"))
    png.SetInputConnection(w2i.GetOutputPort())
    png.Write()
    res["figs"]["layout_3d_png"] = "figs/layout_3d.png"

    exp = vtk.vtkGLTFExporter()
    exp.SetRenderWindow(v.ren_win)
    exp.InlineDataOn()
    exp.SetFileName(str(OUT / "model.gltf"))
    exp.Write()
    gltf_to_glb(OUT / "model.gltf", OUT / "model.glb")
    (OUT / "model.gltf").unlink()
    res["glb"] = "model.glb"


def gltf_to_glb(src: Path, dst: Path) -> None:
    """Pack a glTF with inline data-URI buffers into one binary .glb."""
    import base64
    import struct

    g = json.loads(src.read_text())
    blob = bytearray()
    starts = []
    for b in g["buffers"]:
        data = base64.b64decode(b["uri"].split(",", 1)[1])
        starts.append(len(blob))
        blob += data
        blob += b"\0" * (-len(blob) % 4)
    for bv in g["bufferViews"]:
        bv["byteOffset"] = bv.get("byteOffset", 0) + starts[bv["buffer"]]
        bv["buffer"] = 0
    g["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(dst, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


def write_csvs(res: dict) -> None:
    """Write the plotted curves as CSV files, one column per wavelength."""

    def write(name: str, deg: list, series: dict, unit: str) -> None:
        wavelengths = list(series)
        lines = ["field_deg," + ",".join(f"{unit}_{w}um" for w in wavelengths)]
        for i, d in enumerate(deg):
            lines.append(f"{d:.4f}," + ",".join(f"{series[w][i]:.6g}" for w in wavelengths))
        (OUT / name).write_text("\n".join(lines) + "\n")

    write("rms_spot_vs_field.csv", res["rms"]["deg"], res["rms"]["spot_um"], "rms_spot_um")
    write(
        "rms_wavefront_vs_field.csv",
        res["rms"]["deg_wfe"],
        res["rms"]["wfe_waves"],
        "rms_wfe_waves",
    )
    write("strehl_fft_vs_field.csv", res["strehl"]["deg"], res["strehl"]["fft"], "strehl")


def main(design_dir: Path) -> None:
    configure(design_dir)
    t0 = time.time()
    op_f = load(ZMX_SOURCE, OUT)  # folded, as in Zemax (with thin-lens patch)
    op_u = load(ZMX_SOURCE, OUT, unfolded=True)  # fold replaced by straight propagation
    op = op_u
    res: dict = {"figs": {}, "timings": {}}
    res["wavelengths_um"] = [w.value for w in op.wavelengths.wavelengths]
    res["primary_um"] = op.wavelengths.primary_wavelength.value
    res["fields_deg"] = [float(f.y) for f in op.fields.fields]
    res["EPD"] = float(to_np(op.paraxial.EPD()))
    res["EFL"] = float(to_np(op.paraxial.f2()))
    res["FNO"] = float(to_np(op.paraxial.FNO()))
    res["lens_table"] = lens_table(op_f)

    # Cross-check folded vs unfolded chief-ray image height and BA landing
    xc = []
    for Hy in (0.5, 1.0):
        row = {"Hy": Hy}
        for name, o in (("folded", op_f), ("unfolded", op_u)):
            o.trace_generic(0, Hy, 0, 0, res["primary_um"])
            _, yi = local_xy(o, len(o.surfaces) - 1)
            _, yb = local_xy(o, len(o.surfaces) - 2)
            row[name] = {"image_mm": abs(float(yi[0])), "ba_mm": abs(float(yb[0]))}
        xc.append(row)
    res["fold_check"] = xc

    steps = [
        ("layout", lambda: layout(op_f, res)),
        ("back_aperture", lambda: back_aperture_footprint(op_f, res)),
        ("fov", lambda: focal_plane_fov(op_f, res)),
        ("zemax_comparison", lambda: zemax_comparison_numbers(op_f, res)),
        ("builtin", lambda: builtin_views(op_u, res)),
        ("3d", lambda: export_3d(op_f, res)),
    ]
    for name, fn in steps:
        t = time.time()
        try:
            fn()
        except Exception as exc:  # keep going; record what failed
            import traceback

            res.setdefault("errors", {})[name] = traceback.format_exc()
            print(f"!! {name} failed: {exc!r}")
        res["timings"][name] = round(time.time() - t, 1)
        print(f"{name}: {res['timings'][name]} s")

    t = time.time()
    try:
        deg_w, wfe = rms_vs_field(op_u, res)
        print(f"rms: {round(time.time() - t, 1)} s")
        strehl_vs_field(op_u, res, deg_w, wfe)
    except Exception as exc:
        import traceback

        res.setdefault("errors", {})["rms/strehl"] = traceback.format_exc()
        print(f"!! rms/strehl failed: {exc!r}")

    res["timings"]["total"] = round(time.time() - t0, 1)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    if "rms" in res and "strehl" in res:
        write_csvs(res)
    print("done in", res["timings"]["total"], "s")


if __name__ == "__main__":
    import sys

    main(Path(sys.argv[1]))
