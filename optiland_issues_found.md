# optiland issues found while importing `20260930 SMOD4.5_54SL_250TL.ZMX`

- **optiland version:** 0.6.3 (installed from PyPI via `uv add optiland`, Python 3.15, macOS arm64, numpy backend)
- **Test system:** galvo scan system, 4.5 mm EPD, stop at the galvo.
  - Scan lens: AC508-075-B + LE1015-B, about 54 mm.
  - PBS255 cube.
  - Tube lens: 2 × ACT508-500-B, about 250 mm.
  - 45° fold mirror (`COORDBRK` / `MIRROR` / `COORDBRK`, then negative thicknesses).
  - Objective: Zemax `PARAXIAL` surface, f = 12.5 mm, at the back aperture.
  - Image plane at the back focal plane.
  - Fields 0–10° (angle, y only). Wavelengths 0.94, 0.85 (primary) and 1.10 µm.
- **Working code / workarounds:** `pilot/evaluation/load_system.py`. Exploratory analysis script: `pilot/evaluation/analyze.py`.

**Reference numbers from Zemax:**

- Image semi-diameter is 0.4751 mm, from `DIAM` on the last surface. That includes the marginal rays, so it's an upper bound for the chief ray.
- Expected chief-ray image height at 10° is f_obj · tan(10° · 54/250) ≈ 0.472 mm.

**Status legend:**

- **CONFIRMED:** reproduced, cause located in source.
- **CONFIRMED (cause not located):** reproduced, root cause not yet found.
- **SUSPECTED:** read in source, not yet tested.

---

## 1. `ThinLensInteractionModel` reverses rays travelling in −z (after a mirror) — CONFIRMED, patched locally

**File:** `optiland/interactions/thin_lens_interaction_model.py`, `interact_real_rays`.

**Symptom:** In the folded system, the full-field chief ray reaches the paraxial objective (Zemax surface 21, optiland index 19) travelling +y globally. In the objective's local frame that is N < 0, because the surface follows the mirror and has negative thickness. Coming out of the thin lens, its direction is reversed: global M goes from +0.9993 to −0.992. Rays then "land" on the image plane by propagating backwards. The image height at 10° comes out as 2.71 mm instead of ≈0.47 mm.

**Repro:**

```python
from optiland.fileio import load_zemax_file

op = load_zemax_file("20260930 SMOD4.5_54SL_250TL.ZMX")  # UTF-16 loads fine
op.trace_generic(0, 1.0, 0, 0, 0.85)
s19, s20 = op.surfaces[19], op.surfaces[20]
print(float(s19.M[0]), float(s20.M[0]))  # stock: direction after lens points back
print(492.68 - float(s20.z[0]))  # stock: ~2.71 mm; expected ~0.47 mm
```

**Cause:** for the refractive case the code does

```python
f = self.f * be.copysign(be.ones_like(rays.N), rays.N)  # f flips sign when N<0
f1 = f * n1
f2 = f * n2
L = L * f1 - rays.x
M = M * f1 - rays.y
N = be.where(rays.N > 0, f2, -f2)  # for N<0: -f2 = -(-f*n2) = +f*n2  -> N>0
```

When N < 0, `f` becomes −f, so `f2` is negative. Then `N = -f2` is positive, and the ray is sent back. The sign of `f` also flips for the transverse terms, so the lens acts as diverging toward the "focus". Both sign flips are wrong. The ray should head toward the point `(f·L/|N|, f·M/|N|)` in the back focal plane on the side it is travelling to, and keep the sign of N.

**Fix used locally (verified on this system):**

```python
s = be.copysign(be.ones_like(rays.N), rays.N)
L, M = rays.L / be.abs(rays.N), rays.M / be.abs(rays.N)
L = L * self.f * n1 - rays.x
M = M * self.f * n1 - rays.y
N = s * self.f * n2
if self.f < 0:
    L, M, N = -L, -M, -N
```

**Verification:** with the patch, chief-ray image heights are:

| Hy | Field angle | Image height |
|---|---|---|
| 0.5 | 5° | 0.2377 mm |
| 0.65 | 6.5° | 0.3087 mm |
| 0.7 | 7° | 0.3323 mm |
| 1.0 | 10° | 0.4728 mm |

These are consistent with Zemax (0.475 mm semi-diameter) and with the unfolded model (0.4729 mm at 10°). For N > 0 the patched code gives the same result as the original.

**Still to do for an upstream fix:**

- The **reflective branch** (`is_reflective`) uses `f1 = f2 = -self.f * copysign(1, N)`, then a final `N = -N`. I have not tested it with N < 0 and it deserves the same scrutiny (SUSPECTED).
- Add a regression test: a planar fold mirror followed by a paraxial lens with negative thickness. Image height should equal the unfolded equivalent.
- The `rays.update()` / coating / BSDF ordering in my patch is simplified. It calls `rays.update()` and drops the coating/BSDF branches because this system has neither. An upstream fix should only change the sign logic and keep the rest of the method.

---

## 2. Paraxial engine is wrong for systems with a fold mirror (COORDBRK + MIRROR + negative thicknesses) — CONFIRMED (cause not located)

**Symptom:** paraxial quantities differ between the folded file and an optically identical unfolded version. The unfolded version replaces the flat mirror with a dummy plane and makes the thicknesses after it positive (`unfold_text()` in `load_system.py`). This holds with or without the issue-1 patch, because the paraxial tracer has its own path.

| Quantity | Folded | Unfolded | Real-ray check |
|---|---|---|---|
| XPL | +18.19 mm | −76.35 mm | — |
| XPD | −11.22 mm | −125.88 mm | — |
| Paraxial chief-ray height at image, 10° | −1.286 mm | −0.481 mm | real chief ray 0.4729 mm |
| EFL / FNO | −2.729 / −0.607 | −2.730 / −0.607 | (unaffected) |

**Downstream breakage, all in the folded model:**

- `Distortion` produces divide-by-zero / invalid-value warnings in `100 * (y_real - y_ideal) / y_ideal`.
- `GridDistortion(op)` crashes with `ValueError: zero-size array to reduction operation maximum which has no identity` at `analysis/grid_distortion.py:188` (`be.max(pct[finite])`). Every percentage is non-finite. On the unfolded model it runs: max distortion 1.73 %.
- Anything that uses the exit pupil (wavefront reference sphere, FFT PSF) gets a wrong reference in the folded model.

**Where to look:** `optiland/paraxial.py` and `optiland/paraxial_path.py`. The likely cause is how they treat the sign of thickness/refractive index after a reflection, and coordinate breaks. Zemax's convention is that after a mirror, thicknesses are negative and the index sign flips. The paraxial chief ray at the image is 2.7× too large, which hints at a sign error in the propagation after the mirror, compounded by the thin-lens sign issue in the paraxial (not real) trace of `PARAXIAL` surfaces.

**Repro:**

```python
from load_system import load  # in pilot/evaluation

for unf in (False, True):
    op = load(unfolded=unf)
    print(unf, op.paraxial.XPL(), op.paraxial.XPD(), op.paraxial.chief_ray()[0][-1])
```

**Secondary robustness issue:** `GridDistortion._generate_data` should raise a clear error, or return NaN, when no finite distortion values exist, instead of failing inside `np.max`.

---

## 3. Paraxial (thin) lens is not aberration-free off-axis: big spurious RMS WFE, near-zero Strehl — CONFIRMED (cause not located)

This is the issue that currently blocks the RMS-wavefront-vs-field and Strehl-vs-field requirements.

**Symptom on the real system:** RMS wavefront error grows almost linearly with field, which is not physical. The RMS geometric spot stays at 0.15–1.5 µm, close to the ~0.8 µm Airy radius at NA ≈ 0.64, so the real wavefront cannot be tens of waves.

| Field | RMS WFE (folded, 0.85 µm) | RMS WFE (unfolded) | FFTPSF Strehl |
|---|---|---|---|
| 0° | 0.026 waves | 0.026 waves | 0.974 |
| 5° | ~20 waves | ~21 waves | 0.002 |
| 10° | 43.8 waves | 43.8 waves | 0.0015 |

Unfolding does **not** fix this, so it is separate from issues 1 and 2.

**Minimal repro, stock optiland with no patch:** one ideal paraxial lens, f = 12.5 mm, EPD 4 mm, field 0 and 5°, λ = 0.85 µm:

```python
import numpy as np
from optiland import optic
from optiland.analysis import RmsWavefrontErrorVsField
from optiland.psf import FFTPSF


def build(stop_gap):
    op = optic.Optic()
    op.surfaces.add(index=0, thickness=np.inf)
    op.surfaces.add(index=1, thickness=stop_gap, is_stop=True)
    op.surfaces.add(index=2, surface_type="paraxial", f=12.5, thickness=12.5)
    op.surfaces.add(index=3)
    op.set_aperture(aperture_type="EPD", value=4.0)
    op.fields.set_type("angle")
    op.fields.add(y=0)
    op.fields.add(y=5)
    op.wavelengths.add(0.85, is_primary=True)
    return op


op = build(1e-6)  # stop at the lens
print(RmsWavefrontErrorVsField(op, num_fields=3, num_rays=32)._wavefront_error)
# -> [0, 0.526, 1.291] waves   (ideal lens: expected ~0 at all fields)
print(FFTPSF(op, field=(0, 1), wavelength=0.85, num_rays=128, grid_size=256).strehl_ratio())
# -> 0.159                      (expected ~1.0)

op = build(12.5)  # stop at front focal plane = image-space telecentric (like the real system)
RmsWavefrontErrorVsField(op, num_fields=3, num_rays=32)
# -> ValueError: No valid ray samples found for chief-ray wavefront.  (optiland/wavefront/strategy.py:252)
```

**Likely causes (to investigate):**

1. **OPD term of the thin lens.** `interact_real_rays` adds `opd += f - copysign(sqrt(x²+y²+f²), f)`. That is the phase of a perfect lens for an **on-axis** point only, written in terms of the ray height on the lens. For an off-axis bundle, a perfect lens must make every ray reach the image point `(f·tanθx, f·tanθy)` with equal optical path. That needs a term that depends on the incoming direction, not just the height.
   - Zemax's PARAXIAL surface with `PARM 2` (OPD mode) = 1 (as in this file: `PARM 2 1`) integrates the OPD so the lens is perfect for all fields.
   - A proposed fix is to compute the added OPD so that `OPD_in + n·|P_lens → P_image| = const`. Equivalently, add `−n·(L_out·x + M_out·y)/…`-type terms; check against Zemax's "OPD mode" definition. Also consider exposing the OPD mode as a parameter.
   - The Zemax importer currently ignores `PARM 2` (`fileio/zemax/surfaces.py`, `ParaxialSurfaceHandler.parse` only passes `radius`; `f` comes from `param_0` in `reader/converter.py:166`).
2. **Telecentric / infinite exit pupil.** The chief-ray wavefront strategy fails when the exit pupil is at or near infinity. The real system is close to image-space telecentric, because the galvo is imaged near the objective's front focal plane. The reference-sphere radius should switch to a plane-wave / large-radius treatment instead of returning no samples.
3. The near-linear growth of WFE with field on the real system suggests an uncompensated tilt between the actual wavefront and the reference sphere. That is consistent with 1 and 2 combined.

**Suggested test:** an ideal paraxial lens must give RMS WFE ≈ 0 and Strehl ≈ 1 at every field, for the stop at the lens, the stop at the front focal plane, and the stop elsewhere.

---

## 4. Zemax surface comments (`COMM`) are dropped on import — CONFIRMED (minor)

**Symptom:** `op.info()` shows an empty *Comment* column. The file has comments on several surfaces: `X-galvo`, `AC508-075-B`, `LE1015-B`, `PBS255`, `ACT508-500-B`, `enterance to flip cube`, `underside of filp cube`, `Back aperture`.

**Where:** `optiland/fileio/zemax/reader/parser.py` (no `COMM` handler in the operand table around line 65) and `reader/converter.py` (comment not passed to `surfaces.add`). The `Surface` object needs a `comment` attribute if it doesn't already have one. The writer should round-trip it as well.

**Workaround used:** `zemax_surface_comments()` in `analyze.py` re-reads the `.ZMX` and re-attaches comments by index. It accounts for the two `COORDBRK` surfaces that optiland absorbs (Zemax 17 and 19), which shift the indices after them.

---

## Smaller observations / things that were *not* bugs

- **UTF-16 `.ZMX` files load fine.** I transcoded to UTF-8 preemptively, but `load_zemax_file` reads the original UTF-16 file directly (21 surfaces). The transcode step in `load_system.py` can be removed.
- `op.info()` lists the paraxial surface as **"Planar"**. The surface is actually a `ThinLensInteractionModel` with f = 12.5, so this is only a display issue. It would be clearer as "Paraxial (f=12.5)".
- `surface.semi_aperture` is `None` for surfaces with no physical aperture, but `op.info()` prints a computed semi-aperture. There's no obvious public accessor for the computed (floating) semi-diameter.
- `COORDBRK` surfaces are absorbed into neighbouring surfaces' coordinate systems, so optiland surface indices differ from Zemax indices after each coordinate break. That's not a bug, but it isn't documented on import and it's easy to get wrong.
- The 3D viewer (`draw3D`) opens a VTK desktop window only. For web output I rendered offscreen and exported glTF with `vtkGLTFExporter`.
- There is no STEP export.
- `Optic.trace(Hx, Hy, wavelength, num_rays, distribution)` argument order is easy to get wrong (my mistake, not a bug).

## Priority for fixing

1. **Issue 3** (paraxial lens off-axis OPD + telecentric wavefront). This blocks the Strehl and RMS-WFE requirements for any design that uses an ideal objective.
2. **Issue 1** (thin lens with N < 0). It's small and well understood: a one-function fix plus a test.
3. **Issue 2** (paraxial engine with folds). This blocks distortion and grid distortion on folded files. The workaround is to unfold.
4. **Issue 4** (comments). Cosmetic, but needed for usable prescription reports.
