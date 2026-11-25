# Optiland analysis: twinkle_collection

Our best attempt to make Optiland (0.6.3) reproduce what Zemax stores for `../collection_optics.ZMX`, with the local workarounds in `evaluation_tools/zemax_text.py` and `load_system.py` (tilted surfaces, pickups, galvo configurations, thin-lens patch). Regenerate everything with
`uv run python -m evaluation_tools.analyze_zmx designs/twinkle_collection`.

| File | What it is |
|---|---|
| `results.json` | All numbers behind the page: prescription, semi-diameter check, spots, scan, wavefront probe |
| `figs/relative_illumination.png` | Zemax relative illumination (digitised) against the Optiland pupil fraction |
| `model.glb` | 3D model (glTF binary) for the page's interactive viewer |
| `*_utf8.zmx` | UTF-8 copy of the Zemax file as Optiland reads it (tilted surfaces expanded to coordinate breaks) |
| `figs/layout_rays.png` | Ray paths projected onto the plane of the system (our own plot; Optiland's `draw` mangles folds) |
| `figs/layout_3d.png` | Render from Optiland's VTK 3D viewer |
| `figs/spots.png`, `figs/rms_spot.png` | Spot diagrams and RMS spot radius |
