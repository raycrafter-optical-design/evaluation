# Coordinating optimisation in Optiland and RayCrafter (notes for issue 1)

Starting point: the TWINKLE paper (PLOS ONE, "Teaching advanced methods in neuroscience") says
that optimising beyond the Zemax GUI needs the Zemax API. Their MATLAB script scans lens spacing
and lens types, and the PSF scan behind their Fig 2 reloads the file, sets the galvo tilt, moves
the image plane and saves a Huygens PSF for every one of about 16,000 (angle, z) points.
(`designs/twinkle_excitation/Zemax_reference_output/MATLABStandaloneApplication.m`.)
These are ideas for discussion, not decisions.

## What the evaluation says about where optimising can start

- **Only real-ray merit functions work on the full TWINKLE excitation path today.** Ray tracing
  agrees with Zemax to 0.14% on every stored semi-diameter, but wavefront, PSF and Strehl raise
  `UnsupportedParaxialGeometryError` on tilted or multi-fold systems (issue 8). An optimiser
  using RMS spot radius or chief-ray position can run now. One using Strehl or FWHM cannot.
- **A design must be loaded faithfully before it is optimised.** Three Zemax features are dropped
  silently on import (tilted surfaces, pickups, configurations; issues 5 to 7). An optimiser
  that varies a parameter whose pickup is lost would leave the dependent surface unchanged.
  The workarounds live in `zemax_text.py`; the optimiser should build on the same loader.

## A split that avoids two sources of truth

1. **One model, one loader.** RayCrafter owns the design. Optiland scripts load the design
   through the same path (this repository's `load_system.load`, or its successor in RayCrafter),
   so a result found in a script is the result the GUI would show.
2. **Variables and merit function as data, not code.** A small JSON file next to the design:
   which parameters vary (surface, field, bounds), which configurations count (the 22 galvo
   angles), which merit terms (RMS spot at each angle, chief-ray linearity, later FWHM).
   RayCrafter edits and displays it; a script or a cluster job runs it. This replaces the
   MATLAB loop that rewrites the Zemax file for every point.
3. **Evaluation inside Python, no reloading.** Optiland can change a parameter in memory.
   Reloading the whole file per point is what makes the Zemax route slow. Configurations
   become a list of parameter overrides applied to one model.
4. **Zemax stays the referee.** After an optimisation, export the result to ZMX, open it in
   Zemax, and compare with this repository's checks (semi-diameters, and the PSF plots once
   they can be computed). A design only counts as "working in Optiland" if it passes.

## Questions for Rob

- Is the target the TWINKLE authors' workflow (scan lens spacing and lens types in a catalogue),
  or open-ended local optimisation of curvatures? The first is a discrete search that needs
  fast evaluation more than a clever optimiser; the second needs gradients (Optiland has a
  torch backend) and a PSF that works.
- Should RayCrafter run the optimiser, or only launch scripts and display the trace of
  merit-function values?
- The galvo angle is a configuration, not a lens parameter. Do we want first-class
  multi-configuration support in RayCrafter, given that Optiland drops it on import?
