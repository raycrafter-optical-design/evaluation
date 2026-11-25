"""Draw an optical layout from a loaded Optiland system: glass, mirrors and rays.

Optiland's own ``Optic.draw`` mishandles folded and tilted systems, so we draw from global
coordinates. Every surface profile is built in the surface's local frame (its sag along one
transverse axis) and moved to the global frame with the surface's own rotation and position.
Everything is then projected onto the plane that best fits the ray paths (principal axes).
That is exact for a system that folds in one plane, as these do (the galvo tilts of a few
degrees leave a small out-of-plane component, which the projection drops).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

from evaluation_tools.analyze import to_np

GLASS_COLOUR = "#9fc3d6"
FIELD_COLOURS = ["#1f77b4", "#2ca02c", "#d62728", "#9467bd", "#ff7f0e"]
PROFILE_POINTS = 41


def surface_frame(surface) -> tuple[np.ndarray, np.ndarray]:
    """Global position (3,) and rotation matrix (3, 3) of a surface; ``p = o + R @ local``."""
    cs = surface.geometry.cs
    rotation = to_np(cs.get_rotation_matrix())
    origin = np.array([to_np(c).ravel()[0] for c in cs.position_in_gcs])
    return origin, rotation


def surface_profile(surface, half_height_mm: float, direction: np.ndarray) -> np.ndarray:
    """Global 3D points along the surface, across its local x or y axis (``direction``)."""
    origin, rotation = surface_frame(surface)
    offsets = np.linspace(-half_height_mm, half_height_mm, PROFILE_POINTS)
    local = np.zeros((PROFILE_POINTS, 3))
    local[:, :2] = np.outer(offsets, direction[:2])
    try:
        sag = np.broadcast_to(to_np(surface.geometry.sag(local[:, 0], local[:, 1])), offsets.shape)
        local[:, 2] = np.nan_to_num(sag)
    except Exception:  # noqa: BLE001 - a surface without a sag function is drawn flat
        pass
    return origin + local @ rotation.T


def ray_points(op, hy: float, wavelength_um: float, num_rings: int = 1) -> np.ndarray:
    """Global ray points, shape (rays, surfaces, 3), for surfaces 1 to the image."""
    op.trace(0.0, hy, wavelength_um, num_rings, "hexapolar")
    surfaces = op.surfaces[1:]
    return np.stack(
        [np.stack([to_np(s.x), to_np(s.y), to_np(s.z)], axis=1) for s in surfaces], axis=1
    )


def draw_layout(op, zemax_surfaces: list[dict], fields: list[float], title: str) -> plt.Figure:
    """Layout figure: glass filled, mirrors thick, ideal lenses as arrows, rays for ``fields``.

    ``zemax_surfaces`` supplies the semi-diameters and glasses (same order as ``op.surfaces``).
    ``fields`` are normalised Hy values.
    """
    wavelength = op.wavelengths.primary_wavelength.value
    paths = [ray_points(op, hy, wavelength) for hy in fields]
    points = np.concatenate([p.reshape(-1, 3) for p in paths])
    points = points[np.isfinite(points).all(axis=1)]
    centre = points.mean(axis=0)
    axes = np.linalg.svd(points - centre)[2][:2]  # in-plane axes (2, 3)

    def project(xyz: np.ndarray) -> np.ndarray:
        return (xyz - centre) @ axes.T

    # Largest ray radius per surface sets the drawn size of surfaces with automatic semi-diameter.
    radius = np.zeros(len(op.surfaces))
    for hy in fields:
        op.trace(0.0, hy, wavelength, 12, "hexapolar")
        for index in range(1, len(op.surfaces)):
            origin, rotation = surface_frame(op.surfaces[index])
            local = (
                np.stack(
                    [
                        to_np(op.surfaces[index].x),
                        to_np(op.surfaces[index].y),
                        to_np(op.surfaces[index].z),
                    ],
                    axis=1,
                )
                - origin
            ) @ rotation
            radius[index] = max(radius[index], np.nanmax(np.hypot(local[:, 0], local[:, 1])))

    fig, ax = plt.subplots(figsize=(13, 7))
    outlines: list[np.ndarray | None] = [None]
    for index in range(1, len(op.surfaces)):
        surface, info = op.surfaces[index], zemax_surfaces[index]
        half = info["diam_mm"] if not info["diam_is_automatic"] else 1.05 * radius[index]
        half = max(half, 1.05 * radius[index], 0.2)
        _, rotation = surface_frame(surface)
        # draw across whichever local axis lies most in the plane of the drawing
        in_plane = [np.linalg.norm(axes @ rotation[:, k]) for k in (0, 1)]
        direction = (
            np.array([1.0, 0.0, 0.0]) if in_plane[0] >= in_plane[1] else np.array([0.0, 1.0, 0.0])
        )
        outlines.append(project(surface_profile(surface, half, direction)))

    for index in range(1, len(op.surfaces) - 1):
        info = zemax_surfaces[index]
        if info["glass"] and info["glass"] != "MIRROR" and outlines[index + 1] is not None:
            polygon = np.vstack([outlines[index], outlines[index + 1][::-1]])
            ax.add_patch(
                Polygon(
                    polygon, closed=True, fc=GLASS_COLOUR, ec="#3d6a80", lw=0.8, alpha=0.7, zorder=1
                )
            )
    for index in range(1, len(op.surfaces)):
        info, outline = zemax_surfaces[index], outlines[index]
        if info["glass"] == "MIRROR":
            ax.plot(outline[:, 0], outline[:, 1], color="k", lw=3, zorder=3)
        elif info["type"] == "PARAXIAL":
            ax.plot(
                outline[:, 0],
                outline[:, 1],
                color="#8a5a00",
                lw=1.5,
                ls="-",
                marker="^",
                ms=3,
                zorder=3,
            )
        elif index == len(op.surfaces) - 1:
            ax.plot(outline[:, 0], outline[:, 1], color="k", lw=1, ls="--", zorder=3)
        elif (
            not info["glass"]
            and (outlines[index - 1] is not None)
            and zemax_surfaces[index - 1]["glass"] in ("", None)
        ):
            ax.plot(
                outline[:, 0], outline[:, 1], color="#888", lw=0.6, zorder=2
            )  # stop, filter faces, etc.
    for k, path in enumerate(paths):
        for ray in range(path.shape[0]):
            xy = project(path[ray])
            ax.plot(
                xy[:, 0], xy[:, 1], lw=0.7, color=FIELD_COLOURS[k % len(FIELD_COLOURS)], zorder=2
            )
    ax.set_aspect("equal")
    ax.set_xlabel("in-plane axis 1 (mm)")
    ax.set_ylabel("in-plane axis 2 (mm)")
    ax.set_title(
        title + " (blue: glass, thick black: mirrors, brown: ideal lens, dashed: image plane)",
        fontsize=9,
    )
    ax.grid(alpha=0.25)
    return fig
