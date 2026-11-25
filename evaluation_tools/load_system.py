"""Load a Zemax design into optiland, with a fix for a thin-lens bug.

The .ZMX is UTF-16; optiland's reader expects UTF-8, so we transcode first.

optiland 0.6.3 bug: ThinLensInteractionModel.interact_real_rays forces the
outgoing ray to have local N > 0. After a fold mirror (Zemax negative
thicknesses) rays travel with N < 0, so the paraxial objective sends them back
the way they came. ``patch_thin_lens`` replaces that method with one that
preserves the propagation direction.
"""

from __future__ import annotations

import re
from pathlib import Path

from optiland import backend as be
from optiland.fileio import load_zemax_file
from optiland.interactions.thin_lens_interaction_model import ThinLensInteractionModel

from evaluation_tools.zemax_text import expand_surface_tilts, set_galvo_angle


def _interact_real_rays_fixed(self, rays):
    """Thin-lens refraction that works for rays travelling in either z sense."""
    h2 = rays.x**2 + rays.y**2
    rays.opd = rays.opd + self.f - be.copysign(be.sqrt(h2 + self.f**2), self.f)
    n1 = self.material_pre.n(rays.w)
    n2 = self.material_post.n(rays.w)
    s = be.copysign(be.ones_like(rays.N), rays.N)
    L, M = rays.L / be.abs(rays.N), rays.M / be.abs(rays.N)
    if not be.isinf(self.f):
        # Ray heads for the point (L, M)*f in the back focal plane.
        L = L * self.f * n1 - rays.x
        M = M * self.f * n1 - rays.y
        N = s * self.f * n2
        if self.f < 0:
            L, M, N = -L, -M, -N
    else:
        N = s * n2 / n1
    rays.update()
    rays.L, rays.M, rays.N = L, M, N
    rays.normalize()
    return rays


def patch_thin_lens() -> None:
    ThinLensInteractionModel.interact_real_rays = _interact_real_rays_fixed


def transcode(src: Path, dst: Path) -> Path:
    """Write a UTF-8 copy of the UTF-16 Zemax file ``src`` to ``dst``."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-16"), encoding="utf-8")
    return dst


def unfold_text(text: str) -> str:
    """Replace the 45-degree fold (COORDBRK, MIRROR, COORDBRK) by straight-through
    propagation. The mirror is planar, so this is optically identical, but it lets
    optiland's paraxial engine (pupils, ideal image height) work.

    Surfaces after the fold get their thickness sign flipped; the mirror becomes a
    dummy plane carrying the thickness of the second coordinate break.
    """
    head, *blocks = re.split(r"(?m)^(?=SURF \d+)", text)
    tail_split = re.split(r"(?m)^(?=DMFS|BLNK|MNCA|TOL |MNUM)", blocks[-1], maxsplit=1)
    blocks[-1] = tail_split[0]
    tail = tail_split[1] if len(tail_split) > 1 else ""

    def disz(b):
        return float(re.search(r"(?m)^\s+DISZ (\S+)", b).group(1))

    def set_disz(b, v):
        return re.sub(r"(?m)^(\s+DISZ )\S+", lambda m: f"{m.group(1)}{v!r}", b)

    out, after_fold = [], False
    for b in blocks:
        if re.search(r"(?m)^\s+TYPE COORDBRK", b):
            if after_fold:  # second CB: carry its thickness onto the mirror dummy
                out[-1] = set_disz(out[-1], abs(disz(b)))
            continue
        if re.search(r"(?m)^\s+GLAS MIRROR", b):
            b = re.sub(r"(?m)^\s+GLAS MIRROR.*\n", "", b)
            b = re.sub(r"(?m)^(\s+COMM).*\n", "", b)
            b = b.replace("  TYPE STANDARD", "  COMM fold mirror (unfolded)\n  TYPE STANDARD", 1)
            after_fold = True
            out.append(b)
            continue
        if after_fold:
            d = disz(b)
            b = set_disz(b, -d if d != 0 else 0.0)
        out.append(b)
    out = [re.sub(r"^SURF \d+", f"SURF {i}", b) for i, b in enumerate(out)]
    return head + "".join(out) + tail


def load(
    zmx_source: Path,
    work_dir: Path,
    patched: bool = True,
    unfolded: bool = False,
    galvo_angle_deg: float | None = None,
    suffix: str = "",
):
    """Load ``zmx_source`` into Optiland; intermediate .zmx files are written to ``work_dir``.

    Parameters
    ----------
    galvo_angle_deg : float, optional
        Write this galvo tilt (degrees) into the file, with its pickups, before loading.
        Optiland reads multi-configuration files as configuration 1 only.
    suffix : str
        Appended to the intermediate file names, so several configurations can coexist.

    ``SCBD`` surface tilts are always expanded into coordinate breaks (see ``zemax_text``).
    """
    if patched:
        patch_thin_lens()
    stem = zmx_source.stem
    text = zmx_source.read_text(encoding="utf-16")
    if galvo_angle_deg is not None:
        text = set_galvo_angle(text, galvo_angle_deg)
    text = expand_surface_tilts(text)
    path = work_dir / f"{stem}{suffix}_utf8.zmx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if unfolded:
        upath = path.with_name(f"{stem}{suffix}_unfolded.zmx")
        upath.write_text(unfold_text(path.read_text()))
        path = upath
    return load_zemax_file(str(path))
