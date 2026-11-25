# Optiland analysis: SMOD4.5

Our best attempt to make Optiland (0.6.3, with the local thin-lens patch in `evaluation_tools/load_system.py`) match the Zemax output. Regenerate everything with
`uv run python -m evaluation_tools.analyze designs/SMOD4.5` (about 2 minutes).

| File | What it is |
|---|---|
| `results.json` | All numbers behind the plots and the Zemax comparison (`zemax_comparison` block) |
| `rms_spot_vs_field.csv` | Geometric RMS spot radius (µm) vs scan angle, per wavelength |
| `rms_wavefront_vs_field.csv` | RMS wavefront (waves) vs scan angle. Valid on axis only (Optiland issue 3) |
| `strehl_fft_vs_field.csv` | FFT-PSF Strehl vs scan angle. Valid on axis only |
| `model.glb` | 3D model (glTF binary) exported from Optiland's VTK viewer, used by the page's 3D viewer |
| `*_utf8.zmx` | UTF-8 copy of the Zemax file, as Optiland reads it |
| `*_unfolded.zmx` | Copy with the fold mirror removed (needed for distortion, see issue 2) |
| `figs/layout_yz.png`, `layout_fold.png`, `layout_3d.png` | 2D and 3D layouts |
| `figs/ba_footprint.png`, `ba_conjugation.png` | Back-aperture footprint and conjugation |
| `figs/fov.png` | Chief-ray landing points in the focal plane |
| `figs/spots.png` | Spot diagrams at the five Zemax fields |
| `figs/rms_spot.png`, `rms_wfe.png`, `strehl.png` | RMS spot (valid), RMS wavefront and Strehl (invalid off axis) |
| `figs/field_curvature.png`, `distortion_ftan.png`, `distortion_ftheta.png` | Field curvature and distortion |
| `figs/grid_ftan.png`, `grid_ftheta.png` | Grid distortion |
