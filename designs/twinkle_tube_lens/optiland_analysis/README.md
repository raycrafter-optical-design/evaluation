# Optiland analysis: twinkle_tube_lens

Our best attempt to make Optiland (0.6.3) reproduce what Zemax stores for `../just_tubelens.ZMX`, with the local workarounds in `evaluation_tools/zemax_text.py` and `load_system.py` (tilted surfaces, pickups, galvo configurations, thin-lens patch). Regenerate everything with
`uv run python -m evaluation_tools.analyze_zmx designs/twinkle_tube_lens`.

| File | What it is |
|---|---|
| `results.json` | All numbers behind the page: prescription, semi-diameter check, spots, scan, wavefront probe |
| `figs/chief_ray_position.png` | Chief-ray position on the image plane against galvo angle |
| `model.glb` | 3D model (glTF binary) for the page's interactive viewer |
| `*_utf8.zmx` | UTF-8 copy of the Zemax file as Optiland reads it (tilted surfaces expanded to coordinate breaks) |
| `figs/layout_rays.png` | Ray paths projected onto the plane of the system (our own plot; Optiland's `draw` mangles folds) |
| `figs/layout_3d.png` | Render from Optiland's VTK 3D viewer |
| `figs/spots.png`, `figs/rms_spot.png` | Spot diagrams and RMS spot radius |
