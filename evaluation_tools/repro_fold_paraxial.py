"""Minimal repro: paraxial quantities and GridDistortion on a folded system.

A singlet, a flat 45-degree fold mirror, then either an ideal thin lens (f = 12.5 mm)
or a glass lens, then an image plane. Compared against an optically identical
unfolded system.

"fold fwd"  : elements after the mirror have local +z along the beam.
"fold back" : elements after the mirror have local +z against the beam (what Zemax
              produces with negative thicknesses after a mirror).

Run:  python repro_fold_paraxial.py
"""

import warnings

import numpy as np
from optiland.analysis import GridDistortion
from optiland.optic import Optic


def build(fold: bool, back: bool, kind: str) -> Optic:
    op = Optic()
    op.surfaces.add(index=0, thickness=np.inf)
    op.surfaces.add(index=1, thickness=0, is_stop=True)
    op.surfaces.add(index=2, radius=50, thickness=3, material="N-BK7")  # singlet
    op.surfaces.add(index=3, radius=-50, thickness=40)
    sg = -1 if back else 1
    rx = np.pi / 2 if back else -np.pi / 2  # local z along -y (back) or +y (fwd)
    if fold:
        # flat mirror at z = 43 mm turning the beam to +y
        op.surfaces.add(index=4, material="mirror", rx=np.pi / 4, thickness=0)
        if kind == "thin":
            op.surfaces.add(index=5, surface_type="paraxial", f=12.5, y=30, z=43, rx=rx)
            op.surfaces.add(index=6, y=42.5, z=43, rx=rx)
        else:
            op.surfaces.add(index=5, radius=sg * 30, material="N-BK7", y=30, z=43, rx=rx)
            op.surfaces.add(index=6, radius=-sg * 30, y=34, z=43, rx=rx)
            op.surfaces.add(index=7, y=60, z=43, rx=rx)
    else:
        op.surfaces.add(index=4, thickness=30)  # dummy plane in place of the mirror
        if kind == "thin":
            op.surfaces.add(index=5, surface_type="paraxial", f=12.5, thickness=12.5)
            op.surfaces.add(index=6)
        else:
            op.surfaces.add(index=5, radius=30, thickness=4, material="N-BK7")
            op.surfaces.add(index=6, radius=-30, thickness=26)
            op.surfaces.add(index=7)
    op.set_aperture("EPD", 10)
    op.fields.set_type("angle")
    for y in (0, 5, 10):
        op.fields.add(y=y)
    op.wavelengths.add(0.55, is_primary=True)
    return op


def real_chief_height(op: Optic) -> float:
    """10-degree real chief-ray distance from the axial hit on the image plane."""
    op.trace_generic(0, 0, 0, 0, 0.55)
    a = op.surfaces[-1]
    z0, y0 = float(a.z[0]), float(a.y[0])
    op.trace_generic(0, 1.0, 0, 0, 0.55)
    s = op.surfaces[-1]
    return float(np.hypot(float(s.z[0]) - z0, float(s.y[0]) - y0))


warnings.simplefilter("ignore")
for kind in ("glass", "thin"):
    for fold, back in ((False, False), (True, False), (True, True)):
        op = build(fold, back, kind)
        p = op.paraxial
        y, _ = p.chief_ray()
        try:
            GridDistortion(op)
            gd = "OK"
        except Exception as e:  # noqa: BLE001
            gd = type(e).__name__
        label = "unfolded" if not fold else ("fold back" if back else "fold fwd")
        print(
            f"{kind:5s} {label:9s} | EFL {float(p.f2()):+8.3f}  XPL {float(p.XPL()):+8.3f}  "
            f"paraxial chief {float(y.ravel()[-1]):8.4f}  real chief {real_chief_height(op):8.4f}"
            f"  | GridDistortion: {gd}"
        )
